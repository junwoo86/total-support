"""Pydantic v2 스키마 — 요청/응답 분리.

DB ORM과 1:1이 아니라 UI에 자연스러운 형태로 가공한다.
- 영문 UPPER CODE는 ORM 그대로 (프론트가 토큰 맵으로 라벨 변환)
- 시각은 ISO8601 문자열 (TZ 정보 포함)
- assigned_fields는 콤마 문자열 → 리스트로 분리해서 응답
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# 공통
# ============================================================
class ORMModel(BaseModel):
    """SQLAlchemy 객체를 직접 from_attributes로 변환."""

    model_config = ConfigDict(from_attributes=True)


# ============================================================
# Postings
# ============================================================
class PostingListItem(ORMModel):
    """대시보드 리스트 행 — content_html은 제외."""

    id: int
    source_site: Literal["BIZINFO", "IRIS", "SBA"]
    source_id: str
    title: str
    detail_url: str
    raw_period: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    posting_status: Literal["SCHEDULED", "ONGOING", "CLOSED"]
    assigned_fields: list[str] = Field(default_factory=list)
    ai_suitability: Literal["HIGH", "NORMAL"]
    review_status: Literal["UNREVIEWED", "EXCLUDED", "NEEDS_REVIEW", "IN_PROGRESS"]
    screened_with_version: int
    first_seen_at: datetime
    last_updated_at: datetime
    #: 헬퍼 — UI가 표시할 D-Day (음수=경과). NULL이면 raw_period 노출.
    d_day: int | None = None


class PostingDetail(PostingListItem):
    """단건 조회 — content_html 포함."""

    content_html: str | None = None


class PostingListResponse(BaseModel):
    items: list[PostingListItem]
    total: int
    page: int
    page_size: int


class ReviewStatusPatch(BaseModel):
    status: Literal["UNREVIEWED", "EXCLUDED", "NEEDS_REVIEW", "IN_PROGRESS"]


# ============================================================
# Domains / Keywords
# ============================================================
class DomainOut(ORMModel):
    id: int
    code: str
    label_ko: str
    color: str | None = None
    display_order: int | None = None
    enabled: bool
    created_at: datetime
    updated_at: datetime


class DomainCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9_]+$")
    label_ko: str = Field(min_length=1, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    display_order: int | None = None
    enabled: bool = True


class DomainPatch(BaseModel):
    label_ko: str | None = Field(default=None, max_length=40)
    color: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")
    display_order: int | None = None
    enabled: bool | None = None


MatchMode = Literal["WORD_BOUNDARY", "EXACT_HANGUL", "SUBSTRING", "REGEX"]


class KeywordOut(ORMModel):
    id: int
    domain_id: int
    keyword: str
    match_mode: MatchMode
    case_sensitive: bool
    negative_context: list[str] = Field(default_factory=list)
    enabled: bool
    created_at: datetime
    updated_at: datetime


class KeywordCreate(BaseModel):
    keyword: str = Field(min_length=1, max_length=100)
    match_mode: MatchMode = "WORD_BOUNDARY"
    case_sensitive: bool = False
    negative_context: list[str] = Field(default_factory=list)
    enabled: bool = True


class KeywordPatch(BaseModel):
    keyword: str | None = Field(default=None, max_length=100)
    match_mode: MatchMode | None = None
    case_sensitive: bool | None = None
    negative_context: list[str] | None = None
    enabled: bool | None = None


class KeywordPreviewRequest(BaseModel):
    keyword: str
    match_mode: MatchMode = "WORD_BOUNDARY"
    case_sensitive: bool = False
    negative_context: list[str] = Field(default_factory=list)


class KeywordPreviewMatch(BaseModel):
    posting_id: int
    title: str
    context: str
    start: int
    end: int


class KeywordPreviewResponse(BaseModel):
    matched: int
    scanned: int
    samples: list[KeywordPreviewMatch]


# ============================================================
# Collection runs
# ============================================================
class CollectionRunOut(ORMModel):
    id: int
    source_site: Literal["BIZINFO", "IRIS", "SBA"]
    started_at: datetime
    finished_at: datetime | None = None
    status: Literal["RUNNING", "OK", "WARN", "FAIL"]
    trigger_kind: Literal["SCHEDULE", "MANUAL"]
    triggered_by: str | None = None
    pages_visited: int | None = None
    new_records: int | None = None
    updated_records: int | None = None
    early_break_reason: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


class HealthCard(BaseModel):
    """헬스 패널 카드 1개. 프론트 health-panel.jsx의 데이터 모델과 정합."""

    source_site: Literal["BIZINFO", "IRIS", "SBA"]
    status: Literal["RUNNING", "OK", "WARN", "FAIL"] = "OK"
    latest_run: CollectionRunOut | None = None
    last_ok_at: datetime | None = None
    is_stale: bool = False  # PRD §8.3: 36시간 무수집 감지


class HealthResponse(BaseModel):
    cards: list[HealthCard]
    server_time: datetime


class RunTrigger(BaseModel):
    site: Literal["BIZINFO", "IRIS", "SBA"]


class RunTriggerResponse(BaseModel):
    job_id: str
    site: str
    started_at: datetime
    message: str


# ============================================================
# System logs
# ============================================================
class SystemLogOut(ORMModel):
    id: int
    created_at: datetime
    level: Literal["INFO", "WARN", "ERROR"]
    category: Literal["PARSE_PERIOD", "URL_TRUNCATED", "BACKFILL", "SCRAPER", "API"]
    source_site: str | None = None
    posting_id: int | None = None
    message: str
    payload: dict[str, Any] | None = None
