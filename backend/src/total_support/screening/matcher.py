"""키워드 스크리닝 매처 — PRD §3.3.

4 모드:
- WORD_BOUNDARY  : `\\b{kw}\\b` (영문 단축어 — AI, Bio 등)
- EXACT_HANGUL   : `(?<![가-힣]){kw}(?![가-힣])` (한글 단어)
- SUBSTRING      : `{kw}` (긴 복합어 — Healthcare, 디지털헬스)
- REGEX          : 사용자 정규식 (백오피스에서 직접 입력)

negative_context (§3.3.2):
- 매칭 위치의 좌우 30자 컨텍스트 안에 부정 단어가 있으면 해당 매칭은 무효화
- 컨텍스트 윈도우는 정확히 30자 (PRD 명시)

출력 (PRD §3.2):
- assigned_fields: 매칭된 도메인의 label_ko 콤마 조합 (예: "AI, 헬스케어")
- ai_suitability: 1개 이상 매칭이면 "HIGH", 아니면 "NORMAL"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

from total_support.db.models import MATCH_MODE_VALUES

#: PRD §3.3.2 컨텍스트 윈도우 크기 (좌·우 각각)
CONTEXT_RADIUS: Final[int] = 30


# ============================================================
# 입력/출력 DTO (DB ORM과 분리 — pure function이라 테스트 용이)
# ============================================================
@dataclass(frozen=True, slots=True)
class KeywordSpec:
    """매처에 전달할 키워드 1행. DB 모델과 1:1이지만 ORM 의존을 끊는다."""

    keyword: str
    match_mode: str
    domain_label: str          # 매칭 성공 시 출력에 들어갈 한글 라벨
    case_sensitive: bool = False
    negative_context: tuple[str, ...] = ()
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class MatchHit:
    """단일 매칭 위치 정보 — 디버그/미리보기용."""

    keyword: str
    domain_label: str
    start: int
    end: int
    context: str               # 매칭 위치 좌우 30자 (negative 검사용)


@dataclass(slots=True)
class ScreenResult:
    """screen() 결과. assigned_fields는 PRD §3.2 표기 규칙."""

    domains: list[str] = field(default_factory=list)
    hits: list[MatchHit] = field(default_factory=list)

    @property
    def assigned_fields(self) -> str | None:
        """콤마 조합. 매칭 0건이면 None (DB는 NULL)."""
        return ", ".join(self.domains) if self.domains else None

    @property
    def ai_suitability(self) -> str:
        """1개 이상 매칭이면 HIGH. PRD §3.2."""
        return "HIGH" if self.domains else "NORMAL"


# ============================================================
# 패턴 빌더
# ============================================================
def build_pattern(spec: KeywordSpec) -> re.Pattern[str]:
    """KeywordSpec → 컴파일된 정규식.

    REGEX 모드 외에는 사용자 입력이 그대로 정규식에 들어가지 않도록 escape.
    REGEX 모드는 사용자가 직접 입력한 패턴을 신뢰 (백오피스에서 사전 검증됨).

    Raises:
        re.error: REGEX 모드에서 입력이 잘못된 경우 (백오피스에서 사전 차단됨).
        ValueError: 지원하지 않는 match_mode.
    """
    if spec.match_mode not in MATCH_MODE_VALUES:
        raise ValueError(f"지원하지 않는 match_mode: {spec.match_mode!r}")

    flags = 0 if spec.case_sensitive else re.IGNORECASE

    if spec.match_mode == "REGEX":
        return re.compile(spec.keyword, flags)

    kw_escaped = re.escape(spec.keyword)

    if spec.match_mode == "WORD_BOUNDARY":
        # \b는 영문/숫자 경계 — 한글에는 잘 안 붙으나 PRD 의도대로 영문 단축어용
        return re.compile(rf"\b{kw_escaped}\b", flags)

    if spec.match_mode == "EXACT_HANGUL":
        # 한글 음절이 앞뒤로 붙으면 매칭 안 됨
        return re.compile(rf"(?<![가-힣]){kw_escaped}(?![가-힣])", flags)

    # SUBSTRING — 단순 부분 매칭
    return re.compile(kw_escaped, flags)


# ============================================================
# 메인 함수
# ============================================================
def screen(text: str, keywords: list[KeywordSpec]) -> ScreenResult:
    """본문 텍스트에 대해 전체 키워드를 스캔한다.

    동작:
    1. enabled=True 키워드만 사용
    2. 각 키워드를 모드에 맞게 컴파일 → finditer로 모든 매칭 찾기
    3. 각 매칭마다 좌우 30자 윈도우에서 negative_context 검사 → 통과만 유지
    4. 통과한 매칭의 domain_label을 모은 후, 입력 순서를 유지하며 중복 제거

    Args:
        text: 본문 (title + content_html에서 추출한 텍스트 등 호출자가 조립).
        keywords: 키워드 목록 — 같은 도메인의 키워드가 여럿이면 한 도메인이
            여러 번 매칭될 수 있다. 출력 domains는 자동으로 중복 제거.

    Returns:
        ScreenResult (assigned_fields/ai_suitability 헬퍼 포함).
    """
    if not text or not keywords:
        return ScreenResult()

    hits: list[MatchHit] = []
    matched_domains: list[str] = []
    seen_domains: set[str] = set()

    for spec in keywords:
        if not spec.enabled:
            continue
        try:
            pattern = build_pattern(spec)
        except re.error:
            # 잘못된 REGEX — 시스템 로그에 남기는 책임은 호출자에게
            continue

        any_valid_hit = False
        for m in pattern.finditer(text):
            start, end = m.start(), m.end()
            ctx_start = max(0, start - CONTEXT_RADIUS)
            ctx_end = min(len(text), end + CONTEXT_RADIUS)
            context = text[ctx_start:ctx_end]

            if _is_blocked(context, spec.negative_context, case_sensitive=spec.case_sensitive):
                continue

            any_valid_hit = True
            hits.append(
                MatchHit(
                    keyword=spec.keyword,
                    domain_label=spec.domain_label,
                    start=start,
                    end=end,
                    context=context,
                )
            )

        if any_valid_hit and spec.domain_label not in seen_domains:
            seen_domains.add(spec.domain_label)
            matched_domains.append(spec.domain_label)

    return ScreenResult(domains=matched_domains, hits=hits)


# ============================================================
# 내부 헬퍼
# ============================================================
def _is_blocked(context: str, negatives: tuple[str, ...], *, case_sensitive: bool) -> bool:
    """negative_context 단어 중 하나라도 컨텍스트에 있으면 True."""
    if not negatives:
        return False
    if case_sensitive:
        return any(n and n in context for n in negatives)
    ctx_lower = context.lower()
    return any(n and n.lower() in ctx_lower for n in negatives)
