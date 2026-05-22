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
    ReviewStatusPatch,
)
from total_support.services import postings as svc
from total_support.services.postings import PostingFilter

router = APIRouter(prefix="/postings", tags=["postings"])


@router.get("", response_model=PostingListResponse)
def list_postings(
    db: Annotated[Session, Depends(get_db)],
    status: str | None = Query(default=None, description="review_status 필터"),
    suitability: str | None = Query(default=None, description="ai_suitability 필터"),
    site: str | None = Query(default=None, description="source_site 필터"),
    domain: str | None = Query(default=None, description="assigned_fields LIKE 필터 (label_ko)"),
    hide_expired: bool = Query(default=False, description="PRD §5.2: 만료 자동 숨김"),
    q: str | None = Query(default=None, description="제목/요약 검색"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> PostingListResponse:
    return svc.list_postings(
        db,
        PostingFilter(
            status=status,
            suitability=suitability,
            site=site,
            domain=domain,
            q=q,
            hide_expired=hide_expired,
            page=page,
            page_size=page_size,
        ),
    )


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
