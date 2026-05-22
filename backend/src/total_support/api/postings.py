"""Postings 라우터 — PRD §9 (GET 목록 · PATCH 상태 · GET 상세)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import (
    PostingDetail,
    PostingListItem,
    PostingListResponse,
    ReviewStatusPatch,
)
from total_support.db import GrantPosting, dday_expr, seoul_today_expr
from total_support.observability.logger import LogCategory, LogLevel, log_event

router = APIRouter(prefix="/postings", tags=["postings"])


# --- 헬퍼 ---------------------------------------------------
def _to_list_item(p: GrantPosting, d_day: int | None) -> PostingListItem:
    fields = (
        [f.strip() for f in (p.assigned_fields or "").split(",") if f.strip()]
        if p.assigned_fields
        else []
    )
    return PostingListItem(
        id=p.id,
        source_site=p.source_site,
        source_id=p.source_id,
        title=p.title,
        detail_url=p.detail_url,
        raw_period=p.raw_period,
        start_date=p.start_date,
        end_date=p.end_date,
        posting_status=p.posting_status,
        assigned_fields=fields,
        ai_suitability=p.ai_suitability,
        review_status=p.review_status,
        screened_with_version=p.screened_with_version,
        first_seen_at=p.first_seen_at,
        last_updated_at=p.last_updated_at,
        d_day=d_day,
    )


# --- GET /api/grant/postings -------------------------------
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
    """공고 목록 — 필터 · 페이징 · D-Day 계산.

    PRD §5.2: '검토 필요' 또는 '지원 진행' + hide_expired=True 시
    end_date < 오늘 항목은 제외 (단 end_date NULL인 상시는 항상 노출).
    """
    stmt = select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))

    if status:
        stmt = stmt.where(GrantPosting.review_status == status)
    if suitability:
        stmt = stmt.where(GrantPosting.ai_suitability == suitability)
    if site:
        stmt = stmt.where(GrantPosting.source_site == site)
    if domain:
        # assigned_fields는 콤마 문자열 — LIKE로 부분 매칭
        stmt = stmt.where(GrantPosting.assigned_fields.ilike(f"%{domain}%"))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(GrantPosting.title.ilike(like))

    if hide_expired and status in ("NEEDS_REVIEW", "IN_PROGRESS"):
        stmt = stmt.where(
            (GrantPosting.end_date.is_(None)) | (GrantPosting.end_date >= seoul_today_expr())
        )

    # 총 건수
    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    # 정렬: 적합도 HIGH 우선, D-Day 작은 순, 최근 적재 순
    stmt = stmt.order_by(
        GrantPosting.ai_suitability.asc(),  # HIGH(H) < NORMAL(N) — desc는 반대니 asc 후 보정
        GrantPosting.end_date.asc().nullslast(),
        GrantPosting.first_seen_at.desc(),
    )
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    rows = db.execute(stmt).all()
    items = [_to_list_item(p, d) for (p, d) in rows]
    return PostingListResponse(items=items, total=total, page=page, page_size=page_size)


# --- GET /api/grant/postings/{id}/detail -------------------
@router.get("/{posting_id}/detail", response_model=PostingDetail)
def get_posting_detail(
    posting_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> PostingDetail:
    row = db.execute(
        select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))
        .where(GrantPosting.id == posting_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    p, d_day = row
    base = _to_list_item(p, d_day)
    return PostingDetail(**base.model_dump(), content_html=p.content_html)


# --- PATCH /api/grant/postings/{id}/review-status ----------
@router.patch("/{posting_id}/review-status", response_model=PostingListItem)
def patch_review_status(
    posting_id: int,
    body: ReviewStatusPatch,
    db: Annotated[Session, Depends(get_db)],
) -> PostingListItem:
    row = db.execute(
        select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))
        .where(GrantPosting.id == posting_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="공고를 찾을 수 없습니다")
    p, d_day = row
    old = p.review_status
    if old == body.status:
        return _to_list_item(p, d_day)

    p.review_status = body.status
    log_event(
        db,
        LogLevel.INFO,
        LogCategory.API,
        f"PATCH /api/grant/postings/{posting_id}/review-status → {body.status}",
        posting_id=posting_id,
        payload={"from": old, "to": body.status},
    )
    db.commit()
    db.refresh(p)
    # d_day는 다시 계산 가능하지만 단순화: 기존 값 유지
    return _to_list_item(p, d_day)
