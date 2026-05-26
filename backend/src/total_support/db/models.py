"""ORM 모델 — PRD §4의 5개 테이블.

PRD §4.1: 모든 ENUM류 값은 영문 UPPER CODE로 저장하고 UI에서 라벨을 매핑한다.
물리적으로는 ENUM 타입 대신 VARCHAR + CHECK 제약을 사용한다 (다국어 확장성).

모든 테이블은 `tb_grant_` 접두사를 가진다 (PRD §1.x 모듈 경계).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """모든 tb_grant_* 모델의 공통 베이스."""


# ============================================================
# §4.1 ENUM 코드 집합
# ------------------------------------------------------------
# Python StrEnum 정의는 db/enums.py 에 있다. 여기서는 CHECK
# constraint 가 쓰는 튜플 형태로 re-export 만 한다 (drift 방지).
# ============================================================
from total_support.db.enums import (  # noqa: E402  re-export for migrations/models
    AI_SUITABILITY_VALUES,
    LOG_CATEGORY_VALUES,
    LOG_LEVEL_VALUES,
    MATCH_MODE_VALUES,
    POSTING_STATUS_VALUES,
    REVIEW_STATUS_VALUES,
    RUN_STATUS_VALUES,
    SOURCE_SITE_VALUES,
    TRIGGER_KIND_VALUES,
)


def _check_in(col_name: str, values: tuple[str, ...]) -> CheckConstraint:
    """CHECK (col IN (...)) — 컬럼명 그대로 사용하므로 SQL 인젝션 위험 없음."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{col_name} IN ({quoted})", name=f"ck_{col_name}_enum")


# ============================================================
# §4.2  tb_grant_postings — 메인 테이블
# ============================================================
class GrantPosting(Base):
    __tablename__ = "tb_grant_postings"
    __table_args__ = (
        UniqueConstraint("source_site", "source_id", name="idx_tb_grant_postings_unique"),
        Index("idx_tb_grant_postings_review_status", "review_status"),
        Index("idx_tb_grant_postings_end_date", "end_date"),
        Index("idx_tb_grant_postings_ai_suitability", "ai_suitability"),
        _check_in("source_site", SOURCE_SITE_VALUES),
        _check_in("posting_status", POSTING_STATUS_VALUES),
        _check_in("ai_suitability", AI_SUITABILITY_VALUES),
        _check_in("review_status", REVIEW_STATUS_VALUES),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 출처 / PK
    source_site: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)

    # 본문
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # PRD §4.2: 950자 trim 후 저장 (스크래퍼에서 처리). 컬럼 자체는 1000자.
    detail_url: Mapped[str] = mapped_column(String(1000), nullable=False)
    # PRD §4.2: <script>/<iframe>/onclick 제거된 sanitize 결과 보존.
    content_html: Mapped[str | None] = mapped_column(Text)

    # 접수기간 (PRD §2.3 매트릭스)
    raw_period: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)

    # 상태
    posting_status: Mapped[str] = mapped_column(String(20), nullable=False)

    # 스크리닝
    assigned_fields: Mapped[str | None] = mapped_column(String(200))
    ai_suitability: Mapped[str] = mapped_column(String(10), nullable=False, server_default="NORMAL")
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="UNREVIEWED")
    screened_with_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    # 시각 (TIMESTAMPTZ · DB now() default · 비교는 항상 tz.py 헬퍼)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # 회사 적합도 평가 (마이그레이션 003 · Vertex AI Gemini · ADC)
    # gcp_project_id 또는 회사 지침이 없으면 score=NULL + failed=false.
    # Gemini 3회 재시도 실패 시 score=NULL + failed=true (UI 최상단 "분석 실패").
    relevance_score: Mapped[int | None] = mapped_column(SmallInteger)
    relevance_reason: Mapped[str | None] = mapped_column(Text)
    evaluated_with_guideline_version: Mapped[int | None] = mapped_column(Integer)
    evaluation_failed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )


# ============================================================
# §4.3  tb_grant_domains — 분야 마스터
# ============================================================
class GrantDomain(Base):
    __tablename__ = "tb_grant_domains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    label_ko: Mapped[str] = mapped_column(String(40), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7))
    display_order: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # PRD §4.4: keywords와 1:N · ON DELETE CASCADE
    keywords: Mapped[list["GrantKeyword"]] = relationship(
        back_populates="domain",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ============================================================
# §4.4  tb_grant_keywords — 키워드 자식
# ============================================================
class GrantKeyword(Base):
    __tablename__ = "tb_grant_keywords"
    __table_args__ = (_check_in("match_mode", MATCH_MODE_VALUES),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tb_grant_domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    match_mode: Mapped[str] = mapped_column(String(20), nullable=False, server_default="WORD_BOUNDARY")
    case_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # PRD §3.3.2: 매칭 좌우 30자 컨텍스트에 이 단어가 있으면 매칭 무효
    negative_context: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    domain: Mapped["GrantDomain"] = relationship(back_populates="keywords")


# ============================================================
# §2.4.1  tb_grant_collection_runs — 수집 실행 이력
# ============================================================
class GrantCollectionRun(Base):
    __tablename__ = "tb_grant_collection_runs"
    __table_args__ = (
        _check_in("source_site", SOURCE_SITE_VALUES),
        _check_in("status", RUN_STATUS_VALUES),
        _check_in("trigger_kind", TRIGGER_KIND_VALUES),
        Index("idx_tb_grant_collection_runs_site_started", "source_site", "started_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_site: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    triggered_by: Mapped[str | None] = mapped_column(String(100))
    pages_visited: Mapped[int | None] = mapped_column(Integer)
    new_records: Mapped[int | None] = mapped_column(Integer)
    updated_records: Mapped[int | None] = mapped_column(Integer)
    # ZERO_NEW_PAGE / END_OF_LIST / ERROR / NULL
    early_break_reason: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)


# ============================================================
# §8.1  tb_grant_system_logs — 운영 이벤트 로그
# ============================================================
class GrantSystemLog(Base):
    __tablename__ = "tb_grant_system_logs"
    __table_args__ = (
        _check_in("level", LOG_LEVEL_VALUES),
        _check_in("category", LOG_CATEGORY_VALUES),
        Index("idx_tb_grant_system_logs_created", "created_at"),
        Index("idx_tb_grant_system_logs_level_category", "level", "category"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    source_site: Mapped[str | None] = mapped_column(String(20))
    # NOT a FK — PRD §11.6: 다른 모듈이나 본 모듈 내부 PK 의존성을 피한다.
    # posting이 삭제되어도 로그는 남는다 (감사 추적).
    posting_id: Mapped[int | None] = mapped_column(BigInteger)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


# ============================================================
# §8.2  tb_grant_company_guideline — 회사 적합도 평가용 시스템 지침
# ============================================================
# 단일 row 운영 (id=1 고정). 수정 시 version +1 → UNREVIEWED 공고
# 자동 재평가 트리거. 검토 진행 중/완료된 공고는 historical 값 보존.
class GrantCompanyGuideline(Base):
    __tablename__ = "tb_grant_company_guideline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # 1로 고정
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
