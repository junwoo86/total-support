"""Gemini evaluator — 단위 테스트 (실 호출 없음).

3회 재시도 / JSON 파싱 / score clamp / NULL fallback 을 mock 으로 검증.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from total_support.services import evaluator as ev
from total_support.services.evaluator import EvalResult, GeminiEvaluator, _parse_response


# ============================================================
# get_evaluator — 설정 분기
# ============================================================
def test_get_evaluator_returns_none_when_project_unset(monkeypatch):
    ev.get_evaluator.cache_clear()
    monkeypatch.setenv("TS_GCP_PROJECT_ID", "")
    from total_support.config import get_settings
    get_settings.cache_clear()
    assert ev.get_evaluator() is None
    ev.get_evaluator.cache_clear()


def test_get_evaluator_swallows_sdk_init_failure(monkeypatch):
    ev.get_evaluator.cache_clear()
    monkeypatch.setenv("TS_GCP_PROJECT_ID", "test-project")
    from total_support.config import get_settings
    get_settings.cache_clear()
    with patch.object(GeminiEvaluator, "__init__", side_effect=RuntimeError("ADC missing")):
        assert ev.get_evaluator() is None
    ev.get_evaluator.cache_clear()
    monkeypatch.setenv("TS_GCP_PROJECT_ID", "")
    get_settings.cache_clear()


# ============================================================
# 헬퍼: 실 SDK 우회 인스턴스
# ============================================================
def _make_evaluator():
    inst = GeminiEvaluator.__new__(GeminiEvaluator)
    inst._model_name = "gemini-3.5-flash"
    inst._max_input_chars = 8000
    inst._client = MagicMock()
    return inst


def _response(text: str | None, has_candidates: bool = True):
    if has_candidates:
        return MagicMock(candidates=[MagicMock()], text=text)
    return MagicMock(candidates=[], text=None)


# ============================================================
# 입력 검증
# ============================================================
def test_evaluate_returns_none_for_empty_guideline():
    inst = _make_evaluator()
    assert inst.evaluate(guideline_md="", posting_title="t", posting_body="b"*100) is None
    assert inst.evaluate(guideline_md="   ", posting_title="t", posting_body="b"*100) is None


def test_evaluate_returns_none_for_short_body():
    inst = _make_evaluator()
    assert inst.evaluate(guideline_md="회사지침", posting_title="t", posting_body="짧음") is None


def test_evaluate_truncates_long_body_to_max_chars():
    inst = _make_evaluator()
    inst._client.models.generate_content.return_value = _response(
        '{"score": 70, "reason": "OK"}'
    )
    inst.evaluate(guideline_md="회사지침", posting_title="t", posting_body="가" * 20000)
    sent = inst._client.models.generate_content.call_args.kwargs["contents"]
    # 본문 8000자 + 헤더 ("제목: ...\n\n본문:\n") 길이만큼 더해짐. 본문은 8000 컷.
    assert "가" * 8000 in sent
    assert "가" * 8001 not in sent


# ============================================================
# 성공 path
# ============================================================
def test_evaluate_returns_eval_result_on_success():
    inst = _make_evaluator()
    inst._client.models.generate_content.return_value = _response(
        '{"score": 87, "reason": "AI 진단 영역 핵심 적합 — 회사 방향성 일치."}'
    )
    out = inst.evaluate(guideline_md="우리 회사는 AI 의료 진단", posting_title="t", posting_body="x" * 100)
    assert out == EvalResult(
        score=87,
        reason="AI 진단 영역 핵심 적합 — 회사 방향성 일치."
    )


def test_evaluate_clamps_score_to_0_100():
    inst = _make_evaluator()
    inst._client.models.generate_content.return_value = _response('{"score": 150, "reason": "x"}')
    out = inst.evaluate(guideline_md="g", posting_title="t", posting_body="b"*100)
    assert out.score == 100

    inst._client.models.generate_content.return_value = _response('{"score": -10, "reason": "x"}')
    out = inst.evaluate(guideline_md="g", posting_title="t", posting_body="b"*100)
    assert out.score == 0


def test_evaluate_handles_code_fenced_json():
    """모델이 ```json ... ``` 으로 두를 때도 파싱."""
    raw = '```json\n{"score": 42, "reason": "fenced"}\n```'
    inst = _make_evaluator()
    inst._client.models.generate_content.return_value = _response(raw)
    out = inst.evaluate(guideline_md="g", posting_title="t", posting_body="b"*100)
    assert out is not None
    assert out.score == 42


# ============================================================
# 재시도 path
# ============================================================
def test_evaluate_retries_3_times_on_exception(monkeypatch):
    monkeypatch.setattr(ev.time, "sleep", lambda *_: None)  # 백오프 건너뛰기
    inst = _make_evaluator()
    inst._client.models.generate_content.side_effect = RuntimeError("quota")
    out = inst.evaluate(guideline_md="g", posting_title="t", posting_body="b"*100)
    assert out is None
    assert inst._client.models.generate_content.call_count == 3


def test_evaluate_succeeds_on_2nd_attempt(monkeypatch):
    monkeypatch.setattr(ev.time, "sleep", lambda *_: None)
    inst = _make_evaluator()
    inst._client.models.generate_content.side_effect = [
        RuntimeError("transient"),
        _response('{"score": 55, "reason": "ok"}'),
    ]
    out = inst.evaluate(guideline_md="g", posting_title="t", posting_body="b"*100)
    assert out is not None and out.score == 55
    assert inst._client.models.generate_content.call_count == 2


def test_evaluate_retries_on_invalid_json(monkeypatch):
    monkeypatch.setattr(ev.time, "sleep", lambda *_: None)
    inst = _make_evaluator()
    inst._client.models.generate_content.side_effect = [
        _response("not json at all"),
        _response("also not json"),
        _response('{"score": 33, "reason": "third try"}'),
    ]
    out = inst.evaluate(guideline_md="g", posting_title="t", posting_body="b"*100)
    assert out is not None and out.score == 33


# ============================================================
# _parse_response — 직접 케이스
# ============================================================
def test_parse_response_returns_none_on_safety_block():
    assert _parse_response(_response(None, has_candidates=False)) is None


def test_parse_response_returns_none_on_empty_text():
    assert _parse_response(_response("")) is None


def test_parse_response_handles_score_as_float():
    out = _parse_response(_response('{"score": 87.4, "reason": "x"}'))
    assert out is not None and out.score == 87


def test_parse_response_missing_reason_uses_empty():
    out = _parse_response(_response('{"score": 50}'))
    assert out is not None and out.score == 50 and out.reason == ""
