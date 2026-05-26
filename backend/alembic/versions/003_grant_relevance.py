"""003 · 회사 적합도 평가 (additive only).

추가 항목:
1. tb_grant_company_guideline — 단일 row(id=1) 운영. 회사 설명 + 진행 희망
   지원사업 방향성. version 은 수정 시마다 +1, evaluator 의 입력 지침이 된다.
2. tb_grant_postings 에 평가 결과 3컬럼 (모두 NULL 허용):
     - relevance_score                   SMALLINT  0~100
     - relevance_reason                  TEXT      300자 안팎 자연어
     - evaluated_with_guideline_version  INTEGER   당시 지침 버전

PRD §11.5 운영 DB 비침습:
- 모든 신규 객체는 nullable 또는 server_default 보유 — 기존 데이터 무영향.
- 지침 초기 row 는 빈 문자열 + version=1 로 INSERT (애플리케이션이
  사용자 입력 받기 전까지 비활성 — evaluator 가 "지침 없음" 분기로 통과).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "003_grant_relevance"
down_revision = "002_grant_seed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tb_grant_company_guideline",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("content_md", sa.Text(), nullable=False),
        sa.Column(
            "version", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    # 초기 빈 지침 row — evaluator 는 content_md 가 비면 평가 skip.
    op.execute(
        "INSERT INTO tb_grant_company_guideline (id, content_md, version) "
        "VALUES (1, '', 1)"
    )

    op.add_column(
        "tb_grant_postings",
        sa.Column("relevance_score", sa.SmallInteger(), nullable=True),
    )
    op.add_column(
        "tb_grant_postings",
        sa.Column("relevance_reason", sa.Text(), nullable=True),
    )
    op.add_column(
        "tb_grant_postings",
        sa.Column("evaluated_with_guideline_version", sa.Integer(), nullable=True),
    )
    # 추천 정렬용 인덱스 — relevance_score DESC NULLS LAST
    op.create_index(
        "idx_tb_grant_postings_relevance_score",
        "tb_grant_postings",
        [sa.text("relevance_score DESC NULLS LAST")],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_tb_grant_postings_relevance_score",
        table_name="tb_grant_postings",
    )
    op.drop_column("tb_grant_postings", "evaluated_with_guideline_version")
    op.drop_column("tb_grant_postings", "relevance_reason")
    op.drop_column("tb_grant_postings", "relevance_score")
    op.drop_table("tb_grant_company_guideline")
