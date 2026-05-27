"""Service layer 단위 테스트 — HTTP 우회 직접 호출.

라우터 통합테스트(test_api_*.py)가 end-to-end 흐름을 검증한다면,
이 파일은 서비스 함수가 FastAPI 없이도 도메인 예외를 정확히 raise
하는지 + framework-agnostic 하게 동작하는지를 cover한다.
"""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import LIVE_DB_GUARD_ENABLED, LIVE_DB_GUARD_REASON

pytestmark = pytest.mark.skipif(LIVE_DB_GUARD_ENABLED, reason=LIVE_DB_GUARD_REASON)

from total_support.api.schemas import (
    DomainCreate,
    DomainPatch,
    KeywordCreate,
    KeywordPreviewRequest,
)
from total_support.db.engine import SessionLocal
from total_support.services import domains as svc_domains
from total_support.services import keywords as svc_keywords
from total_support.services import logs as svc_logs
from total_support.services import postings as svc_postings
from total_support.services.exceptions import (
    DuplicateError,
    InvalidPatternError,
    NotFoundError,
    ServiceError,
)
from total_support.services.postings import PostingFilter


# ============================================================
# 도메인 예외 계층
# ============================================================
def test_all_service_errors_subclass_service_error():
    """exception_handler 가 ServiceError 베이스로 잡지 않더라도,
    각 도메인 예외는 ServiceError 의 인스턴스여야 한다 (계약)."""
    assert issubclass(NotFoundError, ServiceError)
    assert issubclass(DuplicateError, ServiceError)
    assert issubclass(InvalidPatternError, ServiceError)


# ============================================================
# domains 서비스 — 라우터 우회 직접 호출
# ============================================================
def test_domains_create_then_patch_then_hard_delete():
    code = f"SVC_UT_{uuid.uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        created = svc_domains.create(
            db, DomainCreate(code=code, label_ko="단위테스트")
        )
        assert created.code == code

        patched = svc_domains.patch(
            db, created.id, DomainPatch(label_ko="수정됨")
        )
        assert patched.label_ko == "수정됨"

        svc_domains.delete(db, created.id, hard=True)

        # 다시 조회하면 없음
        with pytest.raises(NotFoundError):
            svc_domains.patch(db, created.id, DomainPatch(label_ko="X"))


def test_domains_duplicate_code_raises_duplicate_error():
    code = f"SVC_DUP_{uuid.uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        first = svc_domains.create(db, DomainCreate(code=code, label_ko="첫"))
        try:
            with pytest.raises(DuplicateError):
                svc_domains.create(db, DomainCreate(code=code, label_ko="중복"))
        finally:
            svc_domains.delete(db, first.id, hard=True)


def test_domains_patch_unknown_id_raises_not_found():
    with SessionLocal() as db, pytest.raises(NotFoundError):
        svc_domains.patch(db, 9_999_999, DomainPatch(label_ko="x"))


def test_domains_delete_unknown_id_raises_not_found():
    with SessionLocal() as db, pytest.raises(NotFoundError):
        svc_domains.delete(db, 9_999_999, hard=True)


# ============================================================
# keywords 서비스
# ============================================================
def test_keywords_create_on_unknown_domain_raises_not_found():
    with SessionLocal() as db, pytest.raises(NotFoundError):
        svc_keywords.create(db, 9_999_999, KeywordCreate(keyword="x"))


def test_keywords_invalid_regex_raises_invalid_pattern_error():
    code = f"SVC_KW_{uuid.uuid4().hex[:8].upper()}"
    with SessionLocal() as db:
        d = svc_domains.create(db, DomainCreate(code=code, label_ko="kw"))
        try:
            with pytest.raises(InvalidPatternError):
                svc_keywords.create(
                    db,
                    d.id,
                    KeywordCreate(keyword="[unclosed", match_mode="REGEX"),
                )
        finally:
            svc_domains.delete(db, d.id, hard=True)


def test_keywords_preview_invalid_regex_raises_invalid_pattern_error():
    with SessionLocal() as db, pytest.raises(InvalidPatternError):
        svc_keywords.preview(
            db,
            KeywordPreviewRequest(keyword="(?P<unclosed", match_mode="REGEX"),
        )


def test_keywords_preview_basic_returns_response_object():
    with SessionLocal() as db:
        out = svc_keywords.preview(
            db, KeywordPreviewRequest(keyword="AI", match_mode="WORD_BOUNDARY")
        )
        # 스키마 객체로 반환 (라우터 변환 없이)
        assert hasattr(out, "matched")
        assert hasattr(out, "scanned")
        assert hasattr(out, "samples")
        assert out.scanned <= 100


# ============================================================
# postings 서비스
# ============================================================
def test_posting_filter_is_immutable_dataclass():
    """PostingFilter는 frozen — 라우터에서 만든 값이 service 내부에서
    실수로 변경되지 않아야 함."""
    f = PostingFilter(status=("UNREVIEWED",), page=2)
    with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError
        f.page = 5  # type: ignore[misc]


def test_posting_filter_defaults():
    f = PostingFilter()
    assert f.page == 1
    assert f.page_size == 50
    assert f.hide_expired is False
    assert f.status == ()
    assert f.relevance_buckets == ()


def test_postings_list_with_default_filter_returns_response_shape():
    with SessionLocal() as db:
        out = svc_postings.list_postings(db, PostingFilter(page_size=3))
        assert hasattr(out, "items")
        assert hasattr(out, "total")
        assert hasattr(out, "page")
        assert hasattr(out, "page_size")
        assert len(out.items) <= 3


def test_postings_get_detail_unknown_id_raises_not_found():
    with SessionLocal() as db, pytest.raises(NotFoundError):
        svc_postings.get_detail(db, 9_999_999)


def test_postings_patch_unknown_id_raises_not_found():
    with SessionLocal() as db, pytest.raises(NotFoundError):
        svc_postings.patch_review_status(db, 9_999_999, "EXCLUDED")


def test_postings_multi_status_filter_returns_only_those_statuses():
    """다중 status: ('NEEDS_REVIEW','EXCLUDED') 필터 시 각 행의 review_status 가
    둘 중 하나여야 함. UNREVIEWED / IN_PROGRESS 는 섞이지 않음."""
    targets = ("NEEDS_REVIEW", "EXCLUDED")
    with SessionLocal() as db:
        out = svc_postings.list_postings(
            db, PostingFilter(status=targets, page_size=50)
        )
        for item in out.items:
            assert item.review_status in targets


def test_postings_relevance_bucket_high_only_returns_score_ge_80():
    """high 버킷 (80↑) 필터 — 모든 응답 행은 relevance_score >= 80 이어야 함."""
    with SessionLocal() as db:
        out = svc_postings.list_postings(
            db, PostingFilter(relevance_buckets=("high",), page_size=50)
        )
        for item in out.items:
            assert item.relevance_score is not None
            assert item.relevance_score >= 80


def test_postings_relevance_bucket_low_returns_score_lt_40():
    with SessionLocal() as db:
        out = svc_postings.list_postings(
            db, PostingFilter(relevance_buckets=("low",), page_size=50)
        )
        for item in out.items:
            assert item.relevance_score is not None
            assert item.relevance_score < 40


def test_postings_relevance_bucket_multi_high_or_mid_high():
    """다중 버킷: ('high','mid_high') = 60↑ — 모든 응답이 60 이상."""
    with SessionLocal() as db:
        out = svc_postings.list_postings(
            db, PostingFilter(relevance_buckets=("high", "mid_high"), page_size=50)
        )
        for item in out.items:
            assert item.relevance_score is not None
            assert item.relevance_score >= 60


def test_postings_status_counts_sums_match_individual_filtered_lists():
    """get_status_counts 결과가 status 단일 필터 list 의 total 과 일치해야 함."""
    with SessionLocal() as db:
        counts = svc_postings.get_status_counts(db, PostingFilter())
        for status in ("UNREVIEWED", "NEEDS_REVIEW", "IN_PROGRESS", "EXCLUDED"):
            single = svc_postings.list_postings(
                db, PostingFilter(status=(status,), page_size=1)
            )
            assert getattr(counts, status) == single.total, (
                f"counts.{status}={getattr(counts, status)} != list.total={single.total}"
            )


def test_postings_expired_virtual_status_returns_only_unreviewed_past_due():
    """status=('EXPIRED',) → 모두 review_status=UNREVIEWED + end_date < 한국 오늘."""
    from datetime import date, timezone, timedelta
    today_kst = (date.fromtimestamp(__import__('time').time() + 9 * 3600))
    with SessionLocal() as db:
        out = svc_postings.list_postings(
            db, PostingFilter(status=("EXPIRED",), page_size=50)
        )
        for item in out.items:
            assert item.review_status == "UNREVIEWED", item
            assert item.end_date is not None and item.end_date < today_kst, item


def test_postings_expired_count_equals_filtered_list_total():
    """counts.EXPIRED == list_postings(status=EXPIRED).total — 정의 일관성."""
    with SessionLocal() as db:
        counts = svc_postings.get_status_counts(db, PostingFilter())
        listed = svc_postings.list_postings(
            db, PostingFilter(status=("EXPIRED",), page_size=1)
        )
        assert counts.EXPIRED == listed.total


def test_postings_domain_none_returns_only_unmatched():
    """domain=('NONE',) → assigned_fields 가 비어있는(미매칭) 행만."""
    with SessionLocal() as db:
        out = svc_postings.list_postings(
            db, PostingFilter(domain=("NONE",), page_size=50)
        )
        for item in out.items:
            assert not item.assigned_fields, item  # [] 또는 None


def test_postings_domain_real_plus_none_is_union():
    """domain=('AI','NONE') 총합 = AI 매칭 + 미매칭 (서로 겹치지 않음)."""
    with SessionLocal() as db:
        ai = svc_postings.list_postings(db, PostingFilter(domain=("AI",), page_size=1))
        none = svc_postings.list_postings(db, PostingFilter(domain=("NONE",), page_size=1))
        both = svc_postings.list_postings(
            db, PostingFilter(domain=("AI", "NONE"), page_size=1)
        )
        assert both.total == ai.total + none.total


def test_postings_unreviewed_with_hide_expired_excludes_expired_count():
    """UnreviewedTab 자동 적용: status=('UNREVIEWED',) + hide_expired=True
       = 백엔드 UNREVIEWED 전체 - EXPIRED."""
    with SessionLocal() as db:
        counts = svc_postings.get_status_counts(db, PostingFilter())
        active = svc_postings.list_postings(
            db, PostingFilter(status=("UNREVIEWED",), hide_expired=True, page_size=1)
        )
        assert active.total == counts.UNREVIEWED - counts.EXPIRED


# ============================================================
# logs 서비스 — 단순 조회 계약
# ============================================================
def test_logs_list_recent_returns_list_under_limit():
    with SessionLocal() as db:
        out = svc_logs.list_recent(db, limit=5)
        assert isinstance(out, list)
        assert len(out) <= 5


def test_logs_filters_applied_per_arg():
    with SessionLocal() as db:
        for L in svc_logs.list_recent(db, level="INFO", limit=20):
            assert L.level == "INFO"
        for L in svc_logs.list_recent(db, site="BIZINFO", limit=20):
            assert L.source_site == "BIZINFO"
