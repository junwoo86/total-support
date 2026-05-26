"""Vertex AI Gemini 기반 공고 적합도 평가.

수집 시점에 공고(제목 + 본문) 를 회사 지침(시스템 프롬프트)과 함께 LLM 에
보내 0~100 점수 + 평가 사유 자연어를 받는다.

설계 결정 (PRD 보강 논의 — 2026-05-26):
- 모델: `gemini-3.5-flash` (config.gemini_model)
- temperature: **0.0 고정** — 같은 입력 같은 점수 (결정론성)
- 응답: JSON 모드 (`response_mime_type="application/json"`) — 점수/사유 분리 추출
- 재시도: 최대 3회 (지수 backoff 1s / 2s / 4s) — 일시 quota/네트워크 오류 흡수
- 사유 길이: 300자를 목표로 prompt 안내, 실제 응답이 길어도 잘리지 않게
  컬럼/스키마는 TEXT — 그대로 저장 (사용자: "300자 넘기면 절대 안된다는 건 아냐")
- 회사 지침 없음 / ADC 미설정 / 3회 모두 실패 → None 반환 → 적재는 계속.

Biocom-lab/backend/app/llm/client.py 의 google-genai ADC 패턴 차용.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

logger = logging.getLogger(__name__)


# 프롬프트 — 회사 지침은 system_instruction 으로, 공고는 contents 로 전달.
_BASE_INSTRUCTION = """\
당신은 정부/지자체 지원사업 공고를 우리 회사 관점에서 평가하는 전문가입니다.

[우리 회사 지침 / 진행 희망 사업 방향성]
{guideline}

[평가 절차]
1. 사용자가 제공하는 공고의 제목과 본문을 읽습니다.
2. 위 회사 지침과 얼마나 부합하는지 0~100 정수로 판정합니다.
   - 100: 즉시 신청 검토할 수준의 완벽 매치
   - 80~99: 우선 검토 (사업 목표·대상·지원내용이 회사 방향성에 매우 부합)
   - 50~79: 가능성 있음 (일부 영역만 겹침)
   - 20~49: 약함 (간접 연관)
   - 0~19: 무관
3. 점수가 결정된 이유를 한국어로 간결히 설명합니다 (목표 300자 안팎).
   공고에서 인용할 만한 핵심 문구가 있으면 짧게 큰따옴표로 인용합니다.

[출력 형식 — JSON 만 출력. 다른 텍스트 금지]
{{"score": <0~100 정수>, "reason": "<설명>"}}
"""


@dataclass(slots=True, frozen=True)
class EvalResult:
    score: int       # 0~100
    reason: str      # 평가 사유 (300자 안팎, 길어도 truncate 안 함)


class GeminiEvaluator:
    """Vertex AI Gemini 동기 적합도 평가 (JSON 모드 + retry)."""

    MAX_RETRIES = 3
    BACKOFF_BASE_S = 1.0   # 1s → 2s → 4s

    def __init__(
        self,
        *,
        project: str,
        location: str,
        model_name: str,
        timeout_s: float = 30.0,
        max_input_chars: int = 8000,
    ) -> None:
        from google import genai
        from google.genai import types

        self._client = genai.Client(
            vertexai=True,
            project=project,
            location=location,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )
        self._model_name = model_name
        self._max_input_chars = max_input_chars

    @property
    def model_name(self) -> str:
        return self._model_name

    def evaluate(
        self,
        *,
        guideline_md: str,
        posting_title: str,
        posting_body: str,
    ) -> EvalResult | None:
        """평가. 지침이 비었거나 본문이 짧거나 3회 실패 → None."""
        guideline_md = (guideline_md or "").strip()
        if not guideline_md:
            return None
        body = (posting_body or "").strip()
        if len(body) < 30:
            return None
        if len(body) > self._max_input_chars:
            body = body[: self._max_input_chars]

        from google.genai import types
        system_text = _BASE_INSTRUCTION.format(guideline=guideline_md)
        user_text = f"제목: {posting_title}\n\n본문:\n{body}"
        config = types.GenerateContentConfig(
            system_instruction=system_text,
            temperature=0.0,
            max_output_tokens=600,  # 사유가 길어도 잘리지 않도록 여유
            response_mime_type="application/json",
        )

        last_err: Exception | None = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model_name,
                    contents=user_text,
                    config=config,
                )
            except Exception as e:  # noqa: BLE001
                last_err = e
                logger.warning(
                    "Gemini evaluate attempt %d/%d failed: %s",
                    attempt, self.MAX_RETRIES, e,
                )
            else:
                parsed = _parse_response(response)
                if parsed is not None:
                    return parsed
                last_err = RuntimeError("invalid JSON / candidates missing")
            # 마지막 시도 후엔 sleep 안 함
            if attempt < self.MAX_RETRIES:
                time.sleep(self.BACKOFF_BASE_S * (2 ** (attempt - 1)))

        logger.warning("Gemini evaluate giving up after %d retries: %s",
                       self.MAX_RETRIES, last_err)
        return None


# ============================================================
# 응답 파싱 — JSON 모드라도 모델이 가끔 텍스트를 섞어 보내므로 방어적.
# ============================================================
def _parse_response(response) -> EvalResult | None:
    try:
        if not response.candidates:
            return None
        raw = (response.text or "").strip()
        if not raw:
            return None
    except Exception:  # noqa: BLE001
        return None

    # JSON 본문만 잘라내기 (모델이 ```json ... ``` 코드블록을 두를 때 대비)
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        obj = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    score_raw = obj.get("score")
    reason_raw = obj.get("reason", "")
    if not isinstance(score_raw, (int, float)):
        return None
    score = int(round(score_raw))
    score = max(0, min(100, score))   # 0~100 clamp
    reason = str(reason_raw).strip() if reason_raw is not None else ""
    return EvalResult(score=score, reason=reason)


# ============================================================
# 싱글톤 팩토리
# ============================================================
@lru_cache(maxsize=1)
def get_evaluator() -> GeminiEvaluator | None:
    """프로세스 단위 싱글톤. 설정 미비 시 None — 호출자가 None 체크."""
    from total_support.config import get_settings

    s = get_settings()
    if not s.gcp_project_id:
        return None
    try:
        return GeminiEvaluator(
            project=s.gcp_project_id,
            location=s.gemini_location,
            model_name=s.gemini_model,
            timeout_s=s.gemini_timeout_s,
            max_input_chars=s.gemini_max_input_chars,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "Gemini evaluator init failed (ADC missing?): %s — disabled", e
        )
        return None
