"""004 · tb_grant_postings.evaluation_failed 컬럼 추가 (additive only).

목적: Gemini 평가가 3회 재시도 모두 실패한 경우를 명시적으로 식별.
NULL relevance_score 의 두 가지 의미("평가 안 함" vs "시도했으나 실패")를
분리해서 UI 상단에 "분석 실패" 행을 노출할 수 있게 한다.

매트릭스:
  evaluation_failed=false, score=NULL  → 평가 안 함 (지침 비었거나 evaluator 비활성)
  evaluation_failed=false, score=N     → 정상 평가됨
  evaluation_failed=true,  score=NULL  → Gemini 3회 재시도 실패 (UI 최상단 노출)

운영 DB 비침습(PRD §11.5) — NOT NULL + DEFAULT FALSE 로 기존 row 안전 채움.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "004_grant_evaluation_failed"
down_revision = "003_grant_relevance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tb_grant_postings",
        sa.Column(
            "evaluation_failed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tb_grant_postings", "evaluation_failed")
