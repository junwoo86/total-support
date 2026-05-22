"""스크래핑 결과 테이블 제로베이스 리셋.

목적: 수집 파이프라인 회귀 테스트를 위해 공고/실행이력/로그만 비우고
정책 데이터(분야·키워드)는 보존한다.

TRUNCATE 대상 (PRD §4 스크래핑 결과):
  - tb_grant_postings        (공고 데이터)
  - tb_grant_collection_runs (수집 실행 이력)
  - tb_grant_system_logs     (운영 이벤트 로그)

보존 대상 (PRD §3 정책 마스터):
  - tb_grant_domains   (4대 분야 마스터)
  - tb_grant_keywords  (분야별 키워드)

사용:
    python scripts/reset_collection_data.py --yes
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from total_support.config import get_settings  # noqa: E402

TRUNCATE_TABLES = (
    "tb_grant_postings",
    "tb_grant_collection_runs",
    "tb_grant_system_logs",
)

PRESERVE_TABLES = (
    "tb_grant_domains",
    "tb_grant_keywords",
)


def main(argv: list[str]) -> int:
    if "--yes" not in argv:
        print(
            "거부: --yes 플래그 없이는 실행하지 않습니다.\n"
            "  python scripts/reset_collection_data.py --yes",
            file=sys.stderr,
        )
        return 2

    s = get_settings()
    engine = create_engine(
        s.effective_database_url,
        connect_args={"options": f"-c statement_timeout={s.db_statement_timeout_ms}"},
        pool_pre_ping=True,
    )

    with engine.begin() as conn:
        print("── 리셋 전 행 수 ──")
        for t in TRUNCATE_TABLES + PRESERVE_TABLES:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:32s} = {n}")

        print()
        joined = ", ".join(TRUNCATE_TABLES)
        sql = f"TRUNCATE {joined} RESTART IDENTITY CASCADE"
        print(f"실행: {sql}")
        conn.execute(text(sql))

        print()
        print("── 리셋 후 행 수 ──")
        for t in TRUNCATE_TABLES + PRESERVE_TABLES:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  {t:32s} = {n}")

        # 안전 가드: TRUNCATE 대상은 0, 보존 대상은 >0 이어야 함.
        for t in TRUNCATE_TABLES:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            assert n == 0, f"{t} 가 0이 아님 ({n})"
        for t in PRESERVE_TABLES:
            n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            if n == 0:
                print(f"⚠ {t} 가 비어있습니다 — 정책 시드 누락 가능성")

    print("\n완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
