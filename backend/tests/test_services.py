"""Service layer 단위 테스트 — HTTP 우회 직접 호출.

라우터 통합테스트(test_api_*.py)가 end-to-end 흐름을 검증한다면,
이 파일은 서비스 함수가 FastAPI 없이도 도메인 예외를 정확히 raise
하는지 + framework-agnostic 하게 동작하는지를 cover한다.
"""

from __future__ import annotations

import uuid

import pytest

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
    f = PostingFilter(status="UNREVIEWED", page=2)
    with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError
        f.page = 5  # type: ignore[misc]


def test_posting_filter_defaults():
    f = PostingFilter()
    assert f.page == 1
    assert f.page_size == 50
    assert f.hide_expired is False
    assert f.status is None


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
