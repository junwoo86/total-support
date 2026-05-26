"""Postings 서비스 — 목록(필터/페이징/D-Day)·상세·검토상태 변경."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from total_support.api.schemas import (
    PostingDetail,
    PostingListItem,
    PostingListResponse,
)
from total_support.db import GrantPosting, dday_expr, seoul_today_expr
from total_support.observability.logger import LogCategory, LogLevel, log_event
from total_support.services.exceptions import NotFoundError


@dataclass(slots=True, frozen=True)
class PostingFilter:
    """list 쿼리 파라미터를 한 곳에서 표현. 라우터는 Query 검증 후 이 객체로 위임."""

    status: str | None = None
    suitability: str | None = None
    site: str | None = None
    domain: str | None = None
    q: str | None = None
    hide_expired: bool = False
    page: int = 1
    page_size: int = 50


# ============================================================
# 목록
# ============================================================
def list_postings(db: Session, f: PostingFilter) -> PostingListResponse:
    """PRD §5.2: '검토 필요' / '지원 진행' + hide_expired=True 시
    end_date < 오늘 항목 제외 (end_date NULL 인 상시는 항상 노출).
    """
    stmt = select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))

    if f.status:
        stmt = stmt.where(GrantPosting.review_status == f.status)
    if f.suitability:
        stmt = stmt.where(GrantPosting.ai_suitability == f.suitability)
    if f.site:
        stmt = stmt.where(GrantPosting.source_site == f.site)
    if f.domain:
        # assigned_fields 는 콤마 문자열 — LIKE 로 부분 매칭
        stmt = stmt.where(GrantPosting.assigned_fields.ilike(f"%{f.domain}%"))
    if f.q:
        stmt = stmt.where(GrantPosting.title.ilike(f"%{f.q}%"))

    if f.hide_expired and f.status in ("NEEDS_REVIEW", "IN_PROGRESS"):
        stmt = stmt.where(
            (GrantPosting.end_date.is_(None))
            | (GrantPosting.end_date >= seoul_today_expr())
        )

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    # 정렬: 회사 적합도(LLM, 0~100, NULL 후순위) DESC → 키워드 적합도 HIGH 우선
    # → D-Day 작은 순 → 최근 적재 순. relevance 가 없으면 기존 키워드 정렬이 작동.
    stmt = stmt.order_by(
        GrantPosting.relevance_score.desc().nullslast(),
        GrantPosting.ai_suitability.asc(),
        GrantPosting.end_date.asc().nullslast(),
        GrantPosting.first_seen_at.desc(),
    )
    stmt = stmt.offset((f.page - 1) * f.page_size).limit(f.page_size)

    rows = db.execute(stmt).all()
    items = [_to_list_item(p, d) for (p, d) in rows]
    return PostingListResponse(
        items=items, total=total, page=f.page, page_size=f.page_size
    )


# ============================================================
# 상세
# ============================================================
def get_detail(db: Session, posting_id: int) -> PostingDetail:
    row = db.execute(
        select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))
        .where(GrantPosting.id == posting_id)
    ).first()
    if not row:
        raise NotFoundError("공고를 찾을 수 없습니다")
    p, d_day = row
    base = _to_list_item(p, d_day)
    return PostingDetail(**base.model_dump(), content_html=p.content_html)


# ============================================================
# 검토상태 변경 (+ system_logs 적재)
# ============================================================
def patch_review_status(
    db: Session, posting_id: int, new_status: str
) -> PostingListItem:
    row = db.execute(
        select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))
        .where(GrantPosting.id == posting_id)
    ).first()
    if not row:
        raise NotFoundError("공고를 찾을 수 없습니다")
    p, d_day = row
    old = p.review_status
    if old == new_status:
        # no-op: 로그 적재 없이 그대로 반환
        return _to_list_item(p, d_day)

    p.review_status = new_status
    log_event(
        db,
        LogLevel.INFO,
        LogCategory.API,
        f"PATCH /api/grant/postings/{posting_id}/review-status → {new_status}",
        posting_id=posting_id,
        payload={"from": old, "to": new_status},
    )
    db.commit()
    db.refresh(p)
    return _to_list_item(p, d_day)


# ============================================================
# 헬퍼 (ORM → DTO)
# ============================================================
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
        relevance_score=p.relevance_score,
        relevance_reason=p.relevance_reason,
        evaluated_with_guideline_version=p.evaluated_with_guideline_version,
        d_day=d_day,
    )
