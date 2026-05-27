"""DB 없이 동작하는 PostingFilter / bucket / CSV 파서 단위 테스트.

라이브 DB guard 와 무관하게 항상 실행 — 도메인 로직 회귀 가드.
"""

from __future__ import annotations

import pytest

from total_support.api.postings import _csv_tuple
from total_support.services.postings import RELEVANCE_BUCKETS, PostingFilter


# ============================================================
# RELEVANCE_BUCKETS — UI 의 4단계 칩과 1:1 매핑이 깨지면 안 됨
# ============================================================
def test_relevance_buckets_exactly_four_keys():
    assert set(RELEVANCE_BUCKETS.keys()) == {"high", "mid_high", "mid", "low"}


def test_relevance_buckets_cover_full_0_to_100_without_gap_or_overlap():
    """반열림 구간 [min, max) — 합치면 (-∞, +∞) 전체 cover.

    high:    [80, ∞)
    mid_high:[60, 80)
    mid:     [40, 60)
    low:     (-∞, 40)
    """
    assert RELEVANCE_BUCKETS["high"] == (80, None)
    assert RELEVANCE_BUCKETS["mid_high"] == (60, 80)
    assert RELEVANCE_BUCKETS["mid"] == (40, 60)
    assert RELEVANCE_BUCKETS["low"] == (None, 40)

    # 인접 구간 경계 일치
    assert RELEVANCE_BUCKETS["mid_high"][1] == RELEVANCE_BUCKETS["high"][0]
    assert RELEVANCE_BUCKETS["mid"][1] == RELEVANCE_BUCKETS["mid_high"][0]
    assert RELEVANCE_BUCKETS["low"][1] == RELEVANCE_BUCKETS["mid"][0]


# ============================================================
# PostingFilter — 다중값 튜플 기본형
# ============================================================
def test_posting_filter_multi_value_defaults_are_empty_tuples():
    f = PostingFilter()
    assert f.status == ()
    assert f.suitability == ()
    assert f.site == ()
    assert f.domain == ()
    assert f.relevance_buckets == ()


def test_posting_filter_accepts_multi_status_tuple():
    f = PostingFilter(status=("NEEDS_REVIEW", "EXCLUDED"))
    assert f.status == ("NEEDS_REVIEW", "EXCLUDED")


def test_posting_filter_accepts_expired_virtual_status():
    """'EXPIRED' 는 review_status enum 에 없는 가상 토큰 — services 가 SQL 로 해석."""
    f = PostingFilter(status=("NEEDS_REVIEW", "EXPIRED"))
    assert "EXPIRED" in f.status


# ============================================================
# _csv_tuple — 라우터의 다중값 쿼리 파라미터 파서
# ============================================================
@pytest.mark.parametrize(
    "raw, expected",
    [
        (None, ()),
        ("", ()),
        ("UNREVIEWED", ("UNREVIEWED",)),
        ("a,b", ("a", "b")),
        ("a, b ,c", ("a", "b", "c")),       # 공백 trim
        ("a,,b", ("a", "b")),                # 빈 토큰 제거
        (" , ", ()),                         # 전부 빈 토큰
        ("high,mid_high", ("high", "mid_high")),
    ],
)
def test_csv_tuple_parses_multi_value_query(raw, expected):
    assert _csv_tuple(raw) == expected
