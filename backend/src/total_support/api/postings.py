"""Postings 라우터 — HTTP 입출력만 담당.

쿼리/필터/D-Day/log 적재 등 비즈니스 로직은 `services/postings.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import (
    PostingDetail,
    PostingListItem,
    PostingListResponse,
    PostingStatusCounts,
    ReviewStatusPatch,
)
from total_support.services import postings as svc
from total_support.services.postings import PostingFilter

router = APIRouter(prefix="/postings", tags=["postings"])


def _csv_tuple(raw: str | None) -> tuple[str, ...]:
    """쉼표로 구분된 다중값 쿼리 파라미터 → 튜플. 빈 토큰 제거.

    예) "NEEDS_REVIEW,IN_PROGRESS" → ("NEEDS_REVIEW", "IN_PROGRESS")
    UI 의 multi-select 칩이 빈 선택일 때는 파라미터 자체를 보내지 않으므로
    None → () 변환만 처리하면 충분.
    """
    if not raw:
        return ()
    return tuple(t.strip() for t in raw.split(",") if t.strip())


def _build_filter(
    *, status, suitability, site, domain, relevance_bucket,
    q, hide_expired, page, page_size,
) -> PostingFilter:
    return PostingFilter(
        status=_csv_tuple(status),
        suitability=_csv_tuple(suitability),
        site=_csv_tuple(site),
        domain=_csv_tuple(domain),
        relevance_buckets=_csv_tuple(relevance_bucket),
        q=q,
        hide_expired=hide_expired,
        page=page,
        page_size=page_size,
    )


@router.get("", response_model=PostingListResponse)
def list_postings(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, description="review_status 필터 (CSV 다중 가능)"),
    suitability: str | None = Query(default=None, description="ai_suitability 필터 (CSV)"),
    site: str | None = Query(default=None, description="source_site 필터 (CSV)"),
    domain: str | None = Query(default=None, description="assigned_fields LIKE 필터 (CSV)"),
    relevance_bucket: str | None = Query(
        default=None,
        description="회사 적합도 버킷 (high|mid_high|mid|low) CSV — 다중 OR",
    ),
    hide_expired: bool = Query(default=False, description="PRD §5.2: 만료 자동 숨김"),
    q: str | None = Query(default=None, description="제목/요약 검색"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PostingListResponse:
    return svc.list_postings(
        db,
        _build_filter(
            status=status, suitability=suitability, site=site, domain=domain,
            relevance_bucket=relevance_bucket, q=q, hide_expired=hide_expired,
            page=page, page_size=page_size,
        ),
    )


@router.get("/counts", response_model=PostingStatusCounts)
def get_status_counts(
    db: Annotated[Session, Depends(get_db)],
    suitability: str | None = Query(default=None),
    site: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    relevance_bucket: str | None = Query(default=None),
    hide_expired: bool = Query(default=False),
    q: str | None = Query(default=None),
) -> PostingStatusCounts:
    """검토 상태별 카운트 — StatusTab 의 탭 합산/칩 옆 숫자에 사용.

    status 자체는 받지 않음 (4가지 모두 항상 반환). 나머지 필터는 list 와 동일.
    """
    return svc.get_status_counts(
        db,
        _build_filter(
            status=None, suitability=suitability, site=site, domain=domain,
            relevance_bucket=relevance_bucket, q=q, hide_expired=hide_expired,
            page=1, page_size=1,
        ),
    )


@router.get("/evaluate-missing/count")
def evaluate_missing_count(
    db: Annotated[Session, Depends(get_db)],
) -> dict:
    """재평가 대상 건수 — UNREVIEWED + 미만료 + 적합도 비어있음."""
    from total_support.services import guidelines as gsvc

    return {"count": gsvc.count_missing_eval(db)}


@router.post("/evaluate-missing")
def evaluate_missing_trigger() -> dict:
    """적합도 비어있는 미검토 공고 재평가를 백그라운드로 시작.

    대상: review_status=UNREVIEWED AND 미만료 AND
          (relevance_score IS NULL OR evaluation_failed=true).
    본문이 짧거나 비어도 제목 기반 추측 평가 (allow_short).
    Returns: {started, target_count, reason}.
    """
    from total_support.services import guidelines as gsvc

    return gsvc.trigger_fill_missing_async()


@router.get("/evaluate-missing/status")
def evaluate_missing_status() -> dict:
    """재평가 진행 상태 — 프론트 프로그레스바 폴링.

    {running, total, processed, updated, failed, started_at, finished_at}.
    processed/total 로 진행률 계산.
    """
    from total_support.services import guidelines as gsvc

    return gsvc.get_fill_progress()


@router.get("/{posting_id}/detail", response_model=PostingDetail)
def get_posting_detail(
    posting_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PostingDetail:
    return svc.get_detail(db, posting_id)


@router.patch("/{posting_id}/review-status", response_model=PostingListItem)
def patch_review_status(
    posting_id: int,
    body: ReviewStatusPatch,
    db: Annotated[Session, Depends(get_db)],
) -> PostingListItem:
    return svc.patch_review_status(db, posting_id, body.status)
