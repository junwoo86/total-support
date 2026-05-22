"""002 · 시드 데이터 (PRD §3.1).

4대 분야 + 18 키워드를 적재한다.
- 도메인 색상은 프론트 mockdata.js와 정합한다.
- 키워드 매칭 모드는 PRD §3.3.1 권장값(영문 단축=WORD_BOUNDARY,
  한글 단어=EXACT_HANGUL, 긴 복합어=SUBSTRING).
- negative_context는 PRD §3.3.2 시드 예시를 그대로 사용.

PRD §11.10: 시드는 별도 트랜잭션으로 분리되어 적재 실패해도
스키마 마이그레이션은 유효한 상태로 남는다 (Alembic은 리비전 단위로
하나의 트랜잭션을 쓰므로, 002 자체가 분리 단위 역할).
"""

from __future__ import annotations

from alembic import op

revision = "002_grant_seed"
down_revision = "001_grant_initial"
branch_labels = None
depends_on = None


# (code, label_ko, color, display_order)
DOMAINS = [
    ("AI",         "AI",      "#2563eb", 1),
    ("BIO",        "바이오",   "#7c3aed", 2),
    ("HEALTHCARE", "헬스케어", "#ff5a4e", 3),
    ("WELLNESS",   "웰니스",   "#e83e8c", 4),
]

# (domain_code, keyword, match_mode, negative_context_list)
KEYWORDS = [
    # ----- AI -----
    ("AI", "AI",               "WORD_BOUNDARY", ["SAIPA", "AICPA", "SAI"]),
    ("AI", "인공지능",          "EXACT_HANGUL",  []),
    ("AI", "머신러닝",          "EXACT_HANGUL",  []),
    ("AI", "딥러닝",            "EXACT_HANGUL",  []),
    ("AI", "Machine Learning", "SUBSTRING",     []),
    ("AI", "Deep Learning",    "SUBSTRING",     []),
    # ----- BIO -----
    ("BIO", "바이오",   "EXACT_HANGUL",  []),
    ("BIO", "생명공학", "EXACT_HANGUL",  []),
    ("BIO", "Bio",      "WORD_BOUNDARY", ["Biography", "Biology"]),
    ("BIO", "Biotech",  "WORD_BOUNDARY", []),
    # ----- HEALTHCARE -----
    ("HEALTHCARE", "헬스케어",   "EXACT_HANGUL",  []),
    ("HEALTHCARE", "의료",       "EXACT_HANGUL",  ["의료보험 가입 의무", "의료비 공제"]),
    ("HEALTHCARE", "디지털헬스", "SUBSTRING",     []),
    ("HEALTHCARE", "Healthcare", "SUBSTRING",     []),
    ("HEALTHCARE", "Medical",    "WORD_BOUNDARY", []),
    # ----- WELLNESS -----
    ("WELLNESS", "웰니스",   "EXACT_HANGUL",  []),
    ("WELLNESS", "건강증진", "EXACT_HANGUL",  []),
    ("WELLNESS", "Wellness", "SUBSTRING",     []),
]


def upgrade() -> None:
    conn = op.get_bind()

    # ---- 분야 ------------------------------------------------
    # ON CONFLICT(code) DO NOTHING — 재실행 안전
    for code, label_ko, color, order in DOMAINS:
        conn.exec_driver_sql(
            """
            INSERT INTO tb_grant_domains (code, label_ko, color, display_order, enabled)
            VALUES (%s, %s, %s, %s, TRUE)
            ON CONFLICT (code) DO NOTHING
            """,
            (code, label_ko, color, order),
        )

    # ---- 키워드 (domain_id를 code로 lookup) -----------------
    for domain_code, keyword, match_mode, neg in KEYWORDS:
        conn.exec_driver_sql(
            """
            INSERT INTO tb_grant_keywords
                (domain_id, keyword, match_mode, case_sensitive, negative_context, enabled)
            SELECT d.id, %s, %s, FALSE, %s::text[], TRUE
            FROM tb_grant_domains d
            WHERE d.code = %s
              AND NOT EXISTS (
                SELECT 1 FROM tb_grant_keywords k
                WHERE k.domain_id = d.id AND k.keyword = %s
              )
            """,
            (keyword, match_mode, neg, domain_code, keyword),
        )


def downgrade() -> None:
    """시드 정확히 제거 (다른 사용자 추가분은 건드리지 않는다)."""
    conn = op.get_bind()
    seed_codes = tuple(d[0] for d in DOMAINS)
    # 키워드는 도메인 CASCADE로 자동 삭제되므로 도메인만 삭제.
    conn.exec_driver_sql(
        "DELETE FROM tb_grant_domains WHERE code = ANY(%s)",
        (list(seed_codes),),
    )
