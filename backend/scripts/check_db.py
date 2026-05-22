"""Live DB 접속 검증 스크립트.

실행: `python scripts/check_db.py`

확인 항목:
1. 접속 성공 + 서버 버전
2. 현재 user / database / search_path
3. 본 모듈 충돌 검사: `tb_grant_*` 테이블이 이미 존재하는지
4. PRD §11.3 권장 권한 보유 여부 (CREATE on schema)
5. AT TIME ZONE 'Asia/Seoul' 헬퍼 동작 (PRD §2.3.2)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Windows 콘솔(cp949) → UTF-8 강제. 체크/한글 출력에 필요.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# src/ 경로 등록
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import create_engine, text  # noqa: E402

from total_support.config import get_settings  # noqa: E402


def main() -> int:
    s = get_settings()
    # 비밀번호 마스킹 표시
    masked_dsn = s.effective_database_url
    if s.db_password:
        masked_dsn = masked_dsn.replace(s.db_password, "***")
    print(f"DSN  : {masked_dsn}")
    print(f"Host : {s.db_host}:{s.db_port}  DB: {s.db_name}  User: {s.db_user}")
    print()

    engine = create_engine(
        s.effective_database_url,
        connect_args={"options": f"-c statement_timeout={s.db_statement_timeout_ms}"},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as conn:
            ver = conn.execute(text("SHOW server_version")).scalar()
            cur_user = conn.execute(text("SELECT current_user")).scalar()
            cur_db = conn.execute(text("SELECT current_database()")).scalar()
            tz_setting = conn.execute(text("SHOW TimeZone")).scalar()
            print(f"✓ 접속 OK · PostgreSQL {ver}")
            print(f"  current_user     = {cur_user}")
            print(f"  current_database = {cur_db}")
            print(f"  TimeZone (서버)  = {tz_setting}  (변경하지 않음)")

            # 기존 tb_grant_* 충돌 검사
            existing = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name LIKE 'tb_grant_%' "
                    "ORDER BY table_name"
                )
            ).scalars().all()
            print()
            if existing:
                print(f"⚠ 이미 존재하는 tb_grant_* 테이블 {len(existing)}개:")
                for t in existing:
                    print(f"  - {t}")
                print("  → 마이그레이션 전에 이전 시도가 있었는지 확인 필요.")
            else:
                print("✓ tb_grant_* 테이블 충돌 없음 (clean slate)")

            # 다른 모듈 접두사 확인 (참고)
            other_modules = conn.execute(
                text(
                    "SELECT DISTINCT regexp_replace(table_name, '_.+$', '') AS prefix "
                    "FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name LIKE 'tb_%' "
                    "GROUP BY prefix ORDER BY prefix"
                )
            ).scalars().all()
            if other_modules:
                print(f"ℹ 같은 DB에 공존하는 tb_* 모듈 접두사: {', '.join(other_modules)}")

            # AT TIME ZONE helper (PRD §2.3.2)
            seoul_now = conn.execute(
                text("SELECT (now() AT TIME ZONE 'Asia/Seoul')::timestamp")
            ).scalar()
            print(f"✓ AT TIME ZONE 'Asia/Seoul' = {seoul_now}")

            # 권한 (CREATE on public schema)
            can_create = conn.execute(
                text("SELECT has_schema_privilege(current_user, 'public', 'CREATE')")
            ).scalar()
            print(f"  CREATE on public = {can_create}")

        return 0
    except Exception as e:  # noqa: BLE001
        print(f"✗ 접속 실패: {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
