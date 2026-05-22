"""001 · tb_grant_* 초기 스키마 (additive only).

PRD §4 (테이블) + §2.4.1 + §8.1 + §11.5 (트리거) 구현.

이 마이그레이션은 **신규 객체만 생성**하며, 기존 운영 DB의 어떤 객체도
ALTER/DROP/REVOKE하지 않는다 (PRD §11.1 · §11.10).

생성 객체:
  - 5 테이블: tb_grant_postings · tb_grant_domains · tb_grant_keywords
              tb_grant_collection_runs · tb_grant_system_logs
  - 1 시퀀스: tb_grant_keyword_version_seq
  - 1 함수:   fn_tb_grant_bump_keyword_version()
  - 2 트리거: tb_grant_keywords / tb_grant_domains BEFORE INSERT/UPDATE/DELETE

down은 정확한 역순으로 본 모듈 객체만 제거한다.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

# revision identifiers
revision = "001_grant_initial"
down_revision = None
branch_labels = None
depends_on = None


# --- §4.1 ENUM 값 집합 (CHECK 제약으로 강제) -----------------
SOURCE_SITES = ("BIZINFO", "IRIS", "SBA")
POSTING_STATUSES = ("SCHEDULED", "ONGOING", "CLOSED")
AI_SUITABILITIES = ("HIGH", "NORMAL")
REVIEW_STATUSES = ("UNREVIEWED", "EXCLUDED", "NEEDS_REVIEW", "IN_PROGRESS")
RUN_STATUSES = ("RUNNING", "OK", "WARN", "FAIL")
TRIGGER_KINDS = ("SCHEDULE", "MANUAL")
LOG_LEVELS = ("INFO", "WARN", "ERROR")
LOG_CATEGORIES = ("PARSE_PERIOD", "URL_TRUNCATED", "BACKFILL", "SCRAPER", "API")
MATCH_MODES = ("WORD_BOUNDARY", "EXACT_HANGUL", "SUBSTRING", "REGEX")


def _check_in(col: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{v}'" for v in values)
    return f"{col} IN ({quoted})"


def upgrade() -> None:
    # ============================================================
    # 1. 시퀀스 · PRD §3.3.3 / §11.5
    # ============================================================
    op.execute("CREATE SEQUENCE IF NOT EXISTS tb_grant_keyword_version_seq START WITH 1")

    # ============================================================
    # 2. tb_grant_domains · PRD §4.3
    # ============================================================
    op.create_table(
        "tb_grant_domains",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(40), nullable=False, unique=True),
        sa.Column("label_ko", sa.String(40), nullable=False),
        sa.Column("color", sa.String(7)),
        sa.Column("display_order", sa.Integer),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # ============================================================
    # 3. tb_grant_keywords · PRD §4.4
    # ============================================================
    op.create_table(
        "tb_grant_keywords",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "domain_id",
            sa.Integer,
            sa.ForeignKey("tb_grant_domains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("keyword", sa.String(100), nullable=False),
        sa.Column("match_mode", sa.String(20), nullable=False, server_default="WORD_BOUNDARY"),
        sa.Column("case_sensitive", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("negative_context", ARRAY(sa.Text)),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(_check_in("match_mode", MATCH_MODES), name="ck_match_mode_enum"),
    )
    op.create_index("ix_tb_grant_keywords_domain_id", "tb_grant_keywords", ["domain_id"])

    # ============================================================
    # 4. tb_grant_postings · PRD §4.2
    # ============================================================
    op.create_table(
        "tb_grant_postings",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_site", sa.String(20), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        # PRD §4.2: 컬럼 자체는 1000자, 저장 전 950자 trim은 애플리케이션 책임
        sa.Column("detail_url", sa.String(1000), nullable=False),
        sa.Column("content_html", sa.Text),
        sa.Column("raw_period", sa.Text),
        sa.Column("start_date", sa.Date),
        sa.Column("end_date", sa.Date),
        sa.Column("posting_status", sa.String(20), nullable=False),
        sa.Column("assigned_fields", sa.String(200)),
        sa.Column("ai_suitability", sa.String(10), nullable=False, server_default="NORMAL"),
        sa.Column("review_status", sa.String(20), nullable=False, server_default="UNREVIEWED"),
        sa.Column("screened_with_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "source_site", "source_id", name="idx_tb_grant_postings_unique"
        ),
        sa.CheckConstraint(_check_in("source_site", SOURCE_SITES), name="ck_source_site_enum"),
        sa.CheckConstraint(
            _check_in("posting_status", POSTING_STATUSES), name="ck_posting_status_enum"
        ),
        sa.CheckConstraint(
            _check_in("ai_suitability", AI_SUITABILITIES), name="ck_ai_suitability_enum"
        ),
        sa.CheckConstraint(
            _check_in("review_status", REVIEW_STATUSES), name="ck_review_status_enum"
        ),
    )
    op.create_index(
        "idx_tb_grant_postings_review_status", "tb_grant_postings", ["review_status"]
    )
    op.create_index("idx_tb_grant_postings_end_date", "tb_grant_postings", ["end_date"])
    op.create_index(
        "idx_tb_grant_postings_ai_suitability", "tb_grant_postings", ["ai_suitability"]
    )

    # ============================================================
    # 5. tb_grant_collection_runs · PRD §2.4.1
    # ============================================================
    op.create_table(
        "tb_grant_collection_runs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("source_site", sa.String(20), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("trigger_kind", sa.String(20), nullable=False),
        sa.Column("triggered_by", sa.String(100)),
        sa.Column("pages_visited", sa.Integer),
        sa.Column("new_records", sa.Integer),
        sa.Column("updated_records", sa.Integer),
        sa.Column("early_break_reason", sa.String(50)),
        sa.Column("error_message", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.CheckConstraint(
            _check_in("source_site", SOURCE_SITES), name="ck_runs_source_site_enum"
        ),
        sa.CheckConstraint(_check_in("status", RUN_STATUSES), name="ck_runs_status_enum"),
        sa.CheckConstraint(
            _check_in("trigger_kind", TRIGGER_KINDS), name="ck_runs_trigger_kind_enum"
        ),
    )
    op.create_index(
        "idx_tb_grant_collection_runs_site_started",
        "tb_grant_collection_runs",
        ["source_site", "started_at"],
    )

    # ============================================================
    # 6. tb_grant_system_logs · PRD §8.1
    # ============================================================
    op.create_table(
        "tb_grant_system_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("level", sa.String(10), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("source_site", sa.String(20)),
        # PRD §11.6: posting FK를 두지 않는다 (감사 추적 영구 보존)
        sa.Column("posting_id", sa.BigInteger),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("payload", JSONB),
        sa.CheckConstraint(_check_in("level", LOG_LEVELS), name="ck_log_level_enum"),
        sa.CheckConstraint(
            _check_in("category", LOG_CATEGORIES), name="ck_log_category_enum"
        ),
    )
    op.create_index(
        "idx_tb_grant_system_logs_created", "tb_grant_system_logs", ["created_at"]
    )
    op.create_index(
        "idx_tb_grant_system_logs_level_category",
        "tb_grant_system_logs",
        ["level", "category"],
    )

    # ============================================================
    # 7. 키워드 버전 트리거 · PRD §11.5
    # ------------------------------------------------------------
    # 본 모듈 시퀀스만 nextval. 다른 테이블 쓰기 / pg_notify / DDL 금지.
    # ============================================================
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_tb_grant_bump_keyword_version()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          PERFORM nextval('tb_grant_keyword_version_seq');
          RETURN COALESCE(NEW, OLD);
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tb_grant_keywords_bump_version
        BEFORE INSERT OR UPDATE OR DELETE ON tb_grant_keywords
        FOR EACH ROW EXECUTE FUNCTION fn_tb_grant_bump_keyword_version();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tb_grant_domains_bump_version
        BEFORE INSERT OR UPDATE OR DELETE ON tb_grant_domains
        FOR EACH ROW EXECUTE FUNCTION fn_tb_grant_bump_keyword_version();
        """
    )


def downgrade() -> None:
    """역순 정확히 제거 (PRD §11.10). 외부 객체는 절대 손대지 않는다."""
    op.execute("DROP TRIGGER IF EXISTS trg_tb_grant_domains_bump_version ON tb_grant_domains")
    op.execute("DROP TRIGGER IF EXISTS trg_tb_grant_keywords_bump_version ON tb_grant_keywords")
    op.execute("DROP FUNCTION IF EXISTS fn_tb_grant_bump_keyword_version()")

    op.drop_index("idx_tb_grant_system_logs_level_category", table_name="tb_grant_system_logs")
    op.drop_index("idx_tb_grant_system_logs_created", table_name="tb_grant_system_logs")
    op.drop_table("tb_grant_system_logs")

    op.drop_index(
        "idx_tb_grant_collection_runs_site_started", table_name="tb_grant_collection_runs"
    )
    op.drop_table("tb_grant_collection_runs")

    op.drop_index("idx_tb_grant_postings_ai_suitability", table_name="tb_grant_postings")
    op.drop_index("idx_tb_grant_postings_end_date", table_name="tb_grant_postings")
    op.drop_index("idx_tb_grant_postings_review_status", table_name="tb_grant_postings")
    op.drop_table("tb_grant_postings")

    op.drop_index("ix_tb_grant_keywords_domain_id", table_name="tb_grant_keywords")
    op.drop_table("tb_grant_keywords")

    op.drop_table("tb_grant_domains")

    op.execute("DROP SEQUENCE IF EXISTS tb_grant_keyword_version_seq")
