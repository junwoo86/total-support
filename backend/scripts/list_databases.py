"""서버에 어떤 database가 있는지 조회.

`biocom` DB가 없다는 오류 해결을 위한 보조 스크립트.
기본 `postgres` 데이터베이스에 접속해서 가용 DB 목록을 가져온다.
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


def main() -> int:
    s = get_settings()
    # 기본 postgres DB로 접속
    fallback_dsn = (
        f"postgresql+psycopg://{s.db_user}:{s.db_password}"
        f"@{s.db_host}:{s.db_port}/postgres"
    )
    masked = fallback_dsn.replace(s.db_password, "***") if s.db_password else fallback_dsn
    print(f"Fallback DSN: {masked}")
    print()

    engine = create_engine(fallback_dsn, pool_pre_ping=True)
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT datname, pg_size_pretty(pg_database_size(datname)) AS size, "
                    "pg_encoding_to_char(encoding) AS enc, datcollate "
                    "FROM pg_database WHERE datistemplate = false ORDER BY datname"
                )
            ).all()
            print(f"가용 database {len(rows)}개:")
            for r in rows:
                print(f"  - {r.datname:<24} {r.size:>10}  {r.enc:<10}  {r.datcollate}")

            # 현재 user 권한
            cur_user = conn.execute(text("SELECT current_user")).scalar()
            can_create_db = conn.execute(
                text("SELECT rolcreatedb FROM pg_roles WHERE rolname = current_user")
            ).scalar()
            is_super = conn.execute(
                text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
            ).scalar()
            print()
            print(f"current_user = {cur_user}  rolsuper={is_super}  rolcreatedb={can_create_db}")
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"✗ 접속 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
