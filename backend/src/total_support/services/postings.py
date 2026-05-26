"""Postings 서비스 — 목록(필터/페이징/D-Day)·상세·검토상태 변경."""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from total_support.api.schemas import (
    PostingDetail,
    PostingListItem,
    PostingListResponse,
    PostingStatusCounts,
)
from total_support.db import GrantPosting, dday_expr, seoul_today_expr
from total_support.observability.logger import LogCategory, LogLevel, log_event
from total_support.scrapers.bizinfo import BizinfoScraper
from total_support.scrapers.iris import IrisScraper
from total_support.scrapers.sba import SbaScraper
from total_support.services.exceptions import NotFoundError

# 사이트별 본문 selector — scrapers 의 클래스 attribute 단일 출처 재사용.
# 첫 풀 수집(commit 959afc1) 당시엔 selector 가 fetch_detail 에 적용되기 전이라
# 모든 row 의 content_html 이 페이지 전체 sanitize 결과로 저장됨. 상세 응답 시
# 한 번 더 selector 추출을 시도해서 모달에 본문만 노출.
_SITE_BODY_SELECTORS: dict[str, tuple[str, ...]] = {
    BizinfoScraper.SITE_CODE: BizinfoScraper.BODY_SELECTORS,
    IrisScraper.SITE_CODE: IrisScraper.BODY_SELECTORS,
    SbaScraper.SITE_CODE: SbaScraper.BODY_SELECTORS,
}
_BODY_MIN_TEXT_LEN = 50  # BaseScraper.BODY_MIN_TEXT_LEN 과 동일


def _trim_body_html(source_site: str | None, content_html: str | None) -> str | None:
    """저장된 raw content_html 을 사이트별 selector 로 한 번 더 추출.

    - 구 데이터(페이지 전체): selector 가 매치되어 본문만 잘림.
    - 신 데이터(이미 본문 fragment): 같은 selector 가 fragment 안에서도 매치되거나
      매치 실패 시 원본 fragment 그대로 반환되어 idempotent.
    - selector 미정의 / 매치 실패 / parse 오류 → 원본 그대로 (안전 fallback).
    """
    if not content_html or not source_site:
        return content_html
    selectors = _SITE_BODY_SELECTORS.get(source_site, ())
    if not selectors:
        return content_html
    try:
        from selectolax.parser import HTMLParser
        tree = HTMLParser(content_html)
    except Exception:  # noqa: BLE001
        return content_html
    for sel in selectors:
        node = tree.css_first(sel)
        if node is None:
            continue
        txt = (node.text(deep=True, strip=True) or "")
        if len(txt) < _BODY_MIN_TEXT_LEN:
            continue
        html = node.html or ""
        if html:
            return html
    return content_html


# 회사 적합도 점수 (0~100) 버킷 — UI 의 4단계 칩과 1:1 매핑.
# 각 칩은 mutually exclusive 범위 (반열림 구간 [min, max)) — 합치면 0~100 전체 커버.
# evaluation_failed / relevance_score NULL 은 어느 버킷에도 속하지 않음 (별도 노출).
RELEVANCE_BUCKETS: dict[str, tuple[int | None, int | None]] = {
    "high":     (80, None),   # 80 이상
    "mid_high": (60, 80),     # 60~79
    "mid":      (40, 60),     # 40~59
    "low":      (None, 40),   # 39 이하
}


@dataclass(slots=True, frozen=True)
class PostingFilter:
    """list 쿼리 파라미터를 한 곳에서 표현. 라우터는 Query 검증 후 이 객체로 위임.

    status/suitability/site/domain 은 다중 선택 가능 (튜플) — UI 의 multi-select
    칩과 정합. 빈 튜플/None 은 "필터 없음" 으로 동일하게 취급.
    """

    status: tuple[str, ...] = field(default_factory=tuple)
    suitability: tuple[str, ...] = field(default_factory=tuple)
    site: tuple[str, ...] = field(default_factory=tuple)
    domain: tuple[str, ...] = field(default_factory=tuple)
    #: 4단계 적합도 버킷 (RELEVANCE_BUCKETS 의 key) — 다중 선택 시 OR 결합.
    relevance_buckets: tuple[str, ...] = field(default_factory=tuple)
    q: str | None = None
    hide_expired: bool = False
    page: int = 1
    page_size: int = 50


def _apply_common_filters(stmt, f: PostingFilter):
    """list_postings / counts 가 공유하는 필터 적용. status 는 호출자가 별도 처리."""
    if f.suitability:
        stmt = stmt.where(GrantPosting.ai_suitability.in_(f.suitability))
    if f.site:
        stmt = stmt.where(GrantPosting.source_site.in_(f.site))
    if f.domain:
        # assigned_fields 는 콤마 문자열 — 각 도메인 라벨 LIKE 의 OR 결합.
        stmt = stmt.where(
            or_(*[GrantPosting.assigned_fields.ilike(f"%{d}%") for d in f.domain])
        )
    if f.q:
        stmt = stmt.where(GrantPosting.title.ilike(f"%{f.q}%"))
    if f.relevance_buckets:
        clauses = []
        for key in f.relevance_buckets:
            rng = RELEVANCE_BUCKETS.get(key)
            if rng is None:
                continue
            lo, hi = rng
            parts = [GrantPosting.relevance_score.is_not(None)]
            if lo is not None:
                parts.append(GrantPosting.relevance_score >= lo)
            if hi is not None:
                parts.append(GrantPosting.relevance_score < hi)
            clauses.append(and_(*parts))
        if clauses:
            stmt = stmt.where(or_(*clauses))
    return stmt


# ============================================================
# 목록
# ============================================================
def list_postings(db: Session, f: PostingFilter) -> PostingListResponse:
    """PRD §5.2: '검토 필요' / '지원 진행' + hide_expired=True 시
    end_date < 오늘 항목 제외 (end_date NULL 인 상시는 항상 노출).
    """
    stmt = select(GrantPosting, dday_expr(GrantPosting.end_date).label("d_day"))

    if f.status:
        stmt = stmt.where(GrantPosting.review_status.in_(f.status))
    stmt = _apply_common_filters(stmt, f)

    # hide_expired 는 status 가 NEEDS_REVIEW / IN_PROGRESS 와만 교차하는 항목에
    # 의미가 있음. 다중 status 면 그중 하나라도 있으면 적용.
    expirable = {"NEEDS_REVIEW", "IN_PROGRESS"}
    if f.hide_expired and (not f.status or any(s in expirable for s in f.status)):
        stmt = stmt.where(
            (GrantPosting.end_date.is_(None))
            | (GrantPosting.end_date >= seoul_today_expr())
        )

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    # 정렬:
    #  1) evaluation_failed=true 가 최상단 (사용자가 즉시 인지 + 조치)
    #  2) 회사 적합도 LLM 점수 DESC NULLS LAST
    #  3) 키워드 적합도 HIGH 우선
    #  4) D-Day 가까운 순
    #  5) 최근 적재 순
    stmt = stmt.order_by(
        GrantPosting.evaluation_failed.desc(),
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
# 검토 상태별 카운트
# ============================================================
def get_status_counts(db: Session, f: PostingFilter) -> PostingStatusCounts:
    """status 필드를 제외한 같은 필터로 GROUP BY review_status — 4개 모두 반환.

    StatusTab 의 탭 옆 합산 카운트 + 칩별 카운트 표시에 사용. domain/q/
    hide_expired 등 다른 필터가 함께 들어오면 그 조건 하에서의 분포를 보여줌.
    f.status 와 f.page/page_size 는 무시.
    """
    base = select(
        GrantPosting.review_status,
        func.count().label("c"),
    )
    base = _apply_common_filters(base, f)
    if f.hide_expired:
        base = base.where(
            (GrantPosting.end_date.is_(None))
            | (GrantPosting.end_date >= seoul_today_expr())
        )
    base = base.group_by(GrantPosting.review_status)

    counts = PostingStatusCounts()
    for status, c in db.execute(base).all():
        if hasattr(counts, status):
            setattr(counts, status, int(c))
    return counts


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
    trimmed = _trim_body_html(p.source_site, p.content_html)
    return PostingDetail(**base.model_dump(), content_html=trimmed)


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
        evaluation_failed=p.evaluation_failed,
        d_day=d_day,
    )
