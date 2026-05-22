"""parse_period() 12 케이스 — PRD §2.3 매트릭스 정합 검증.

PRD §10 체크리스트: "접수기간 파서 — §2.3 매트릭스 테스트 케이스 12개로 검증".
사이트별 실측 사례(§2.1)를 모두 커버한다.
"""

from __future__ import annotations

from datetime import date

import pytest
from freezegun import freeze_time

from total_support.parsers.period import parse_period


# ============================================================
# 12 케이스 — (id, raw, expected_start, expected_end, expected_rule, expected_end_time?)
# ============================================================
CASES = [
    # ---- P1 (ISO date · 다양한 구분자) ----
    pytest.param(
        "BIZINFO 실측 (점 구분, 공백 ~)",
        "2026.05.20 ~ 2026.06.08",
        date(2026, 5, 20), date(2026, 6, 8), "P1", None,
        id="P1_bizinfo_dot",
    ),
    pytest.param(
        "IRIS 실측 (대시 구분)",
        "2026-05-22 ~ 2026-06-22",
        date(2026, 5, 22), date(2026, 6, 22), "P1", None,
        id="P1_iris_dash",
    ),
    pytest.param(
        "SBA 실측 (대시 구분)",
        "2026-06-01 ~ 2026-06-27",
        date(2026, 6, 1), date(2026, 6, 27), "P1", None,
        id="P1_sba_dash",
    ),
    pytest.param(
        "슬래시 구분",
        "2026/03/01 ~ 2026/03/31",
        date(2026, 3, 1), date(2026, 3, 31), "P1", None,
        id="P1_slash",
    ),
    pytest.param(
        "end만 (단일 날짜)",
        "마감 2026-06-22",
        None, date(2026, 6, 22), "P1", None,
        id="P1_end_only",
    ),
    # ---- P2 (시간 정보 포함) ----
    pytest.param(
        "IRIS 사례2 — 요일/시간 부속",
        "2026.05.22(금) ~ 06.22(월) 18:00 까지",
        date(2026, 5, 22), date(2026, 6, 22), "P2", "18:00",
        id="P2_iris_with_time",
    ),
    # ---- P3 (연도 생략 · 단편형) ----
    pytest.param(
        "연도 생략 단편형",
        "~ 06.22",
        None, date(2026, 6, 22), "P3", None,
        id="P3_year_omitted",
    ),
    # ---- P4 (상시/예산 소진) ----
    pytest.param(
        "상시모집",
        "상시모집",
        None, None, "P4", None,
        id="P4_always",
    ),
    pytest.param(
        "예산 소진 시까지",
        "예산 소진 시까지",
        None, None, "P4", None,
        id="P4_budget_exhausted",
    ),
    pytest.param(
        "상시모집 (예산 소진 시 마감) — 복합",
        "상시모집 (예산 소진 시 마감)",
        None, None, "P4", None,
        id="P4_combined",
    ),
    # ---- P5 (공고일로부터 N일) ----
    pytest.param(
        "공고일로부터 30일 (announce_date 없음 → end NULL)",
        "공고일로부터 30일",
        None, None, "P5", None,
        id="P5_no_announce",
    ),
    # ---- P6 (PARSE_UNKNOWN) ----
    pytest.param(
        "P6 — 자유 자연어",
        "추후 공지",
        None, None, "P6", None,
        id="P6_unknown",
    ),
]


@freeze_time("2026-05-22")
@pytest.mark.parametrize(
    "label,raw,exp_start,exp_end,exp_rule,exp_time", CASES
)
def test_parse_period_matrix(label, raw, exp_start, exp_end, exp_rule, exp_time):
    """PRD §2.3 12 케이스."""
    out = parse_period(raw)
    assert out.start_date == exp_start, f"{label}: start_date mismatch"
    assert out.end_date == exp_end, f"{label}: end_date mismatch"
    assert out.rule == exp_rule, f"{label}: rule={out.rule} (expected {exp_rule})"
    assert out.end_time == exp_time, f"{label}: end_time={out.end_time}"
    # raw_period는 항상 원문(strip 정도) 보존
    assert raw.strip() in out.raw_period or out.raw_period == raw.strip()


@freeze_time("2026-05-22")
def test_parse_period_p5_with_announce_date():
    """P5 — announce_date 주면 end_date 계산."""
    out = parse_period("공고일로부터 30일", announce_date=date(2026, 5, 22))
    assert out.start_date == date(2026, 5, 22)
    assert out.end_date == date(2026, 6, 21)
    assert out.rule == "P5"


@freeze_time("2026-05-22")
def test_parse_period_invalid_date_falls_to_p6():
    """잘못된 날짜값(2026-13-40)은 P6로 떨어진다."""
    out = parse_period("2026-13-40 ~ 2026-14-50")
    assert out.start_date is None
    assert out.end_date is None
    assert out.rule == "P6"


@freeze_time("2026-05-22")
def test_parse_period_raw_preserved():
    """raw_period는 손실 없이 원문 보존 (PRD §2.3)."""
    raw = "2026.05.22(금) ~ 06.22(월) 18:00 까지"
    out = parse_period(raw)
    assert out.raw_period == raw  # 원문 그대로


def test_parse_period_none_raises():
    """None 입력은 명시적 오류."""
    import pytest as p
    with p.raises(ValueError):
        parse_period(None)  # type: ignore[arg-type]
