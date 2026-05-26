"""dashboard-dev → dashboard 데이터 일회성 동기화.

전제: prod 에는 `alembic upgrade head` 가 이미 적용되어 스키마/시퀀스/
트리거/시드(4 도메인 + 18 키워드 + 빈 지침 v1) 가 만들어진 상태여야 함.

이 스크립트가 하는 일:
  1. dev 의 각 테이블 모든 행 + 시퀀스 last_value 수집 (read-only)
  2. prod 에서 ALTER TABLE ... DISABLE TRIGGER USER (domains/keywords)
  3. TRUNCATE 6 data tables RESTART IDENTITY CASCADE
  4. dev 행 그대로 INSERT (id 보존)
  5. setval() 7 sequences = dev last_value (트리거 카운터 포함)
  6. ENABLE TRIGGER USER
  7. COUNT 대조 — 1건이라도 불일치하면 ROLLBACK

전체가 prod 측 단일 트랜잭션. 실패 시 prod 변경 0.
"""

from __future__ import annotations

import io
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import psycopg
from psycopg.types.json import Jsonb

DEV = "postgresql://postgres:bico0211@34.47.95.104:5432/dashboard-dev"
PROD = "postgresql://postgres:bico0211@34.47.95.104:5432/dashboard"

# tb_grant_alembic_version 은 alembic 이 관리 — 양쪽 모두 같은 revision 이미
# 보장됨 (한 번에 head 까지 올라간 상태). 데이터 카피 대상에서 제외.
DATA_TABLES = [
    # FK-safe: domains 먼저, keywords 가 domains.id 참조
    "tb_grant_domains",
    "tb_grant_keywords",
    "tb_grant_postings",
    "tb_grant_collection_runs",
    "tb_grant_system_logs",
    "tb_grant_company_guideline",
]

SEQUENCES = [
    "tb_grant_domains_id_seq",
    "tb_grant_keywords_id_seq",
    "tb_grant_postings_id_seq",
    "tb_grant_collection_runs_id_seq",
    "tb_grant_system_logs_id_seq",
    "tb_grant_company_guideline_id_seq",
    "tb_grant_keyword_version_seq",  # 트리거 카운터 — 어느 테이블 소유도 아님
]

# 트리거가 달려있는 테이블 (INSERT 시 자동 sequence bump 방지)
TRIGGER_TABLES = ["tb_grant_domains", "tb_grant_keywords"]


def get_columns_with_types(conn, table) -> list[tuple[str, str]]:
    """반환: [(column_name, udt_name)]. udt_name 으로 'jsonb' 식별."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, udt_name
            FROM information_schema.columns
            WHERE table_schema='public' AND table_name=%s
            ORDER BY ordinal_position
            """,
            (table,),
        )
        return [(r[0], r[1]) for r in cur.fetchall()]


def main() -> int:
    print("=" * 70)
    print("1. dev 데이터 + 시퀀스 last_value 수집 (read-only)")
    print("=" * 70)
    table_data: dict[str, tuple[list[str], list[tuple]]] = {}
    seq_values: dict[str, int] = {}

    with psycopg.connect(DEV) as dc:
        with dc.cursor() as cur:
            for seq in SEQUENCES:
                cur.execute(f"SELECT last_value FROM {seq}")
                seq_values[seq] = cur.fetchone()[0]
                print(f"  seq {seq:50s} = {seq_values[seq]}")
        for t in DATA_TABLES:
            cols_types = get_columns_with_types(dc, t)
            cols = [c for c, _ in cols_types]
            with dc.cursor() as cur:
                cur.execute(f'SELECT {",".join(cols)} FROM {t} ORDER BY id NULLS LAST')
                rows = cur.fetchall()
            table_data[t] = (cols_types, rows)
            print(f"  {t:42s} rows={len(rows):4d}  cols={len(cols)}")

    print()
    print("=" * 70)
    print("2. prod 단일 트랜잭션 — disable trig → truncate → insert → setval → verify")
    print("=" * 70)
    with psycopg.connect(PROD, autocommit=False) as pc:
        try:
            with pc.cursor() as cur:
                # 2a. 사용자 트리거 비활성 (FK/시스템 트리거는 유지)
                for t in TRIGGER_TABLES:
                    cur.execute(f"ALTER TABLE {t} DISABLE TRIGGER USER")
                    print(f"  [trig] DISABLE USER on {t}")

                # 2b. TRUNCATE — prod 의 시드(4+18+1)와 임의 잔여 데이터 제거
                trunc_list = ", ".join(DATA_TABLES)
                cur.execute(f"TRUNCATE {trunc_list} RESTART IDENTITY CASCADE")
                print(f"  [truncate] {len(DATA_TABLES)} tables")

                # 2c. dev 행 그대로 INSERT (id 컬럼 포함)
                # jsonb 컬럼만 선택적으로 Jsonb 로 wrap — text[] / 다른 ARRAY 는
                # psycopg 가 list 그대로 처리하므로 건드리면 안 됨.
                for t in DATA_TABLES:
                    cols_types, rows = table_data[t]
                    if not rows:
                        print(f"  [insert] {t:42s} skip (0 rows)")
                        continue
                    jsonb_idx = {
                        i for i, (_, udt) in enumerate(cols_types) if udt == "jsonb"
                    }
                    placeholders = ",".join(["%s"] * len(cols_types))
                    col_list = ",".join(f'"{c}"' for c, _ in cols_types)
                    wrapped = [
                        tuple(
                            Jsonb(v) if (i in jsonb_idx and v is not None) else v
                            for i, v in enumerate(row)
                        )
                        for row in rows
                    ]
                    cur.executemany(
                        f"INSERT INTO {t}({col_list}) VALUES ({placeholders})",
                        wrapped,
                    )
                    print(f"  [insert] {t:42s} {len(rows):4d} rows"
                          + (f"  (jsonb cols: {sorted(jsonb_idx)})" if jsonb_idx else ""))

                # 2d. 시퀀스 = dev last_value 강제
                for seq in SEQUENCES:
                    cur.execute("SELECT setval(%s, %s, true)", (seq, seq_values[seq]))
                    print(f"  [setval] {seq:50s} = {seq_values[seq]}")

                # 2e. 트리거 재활성
                for t in TRIGGER_TABLES:
                    cur.execute(f"ALTER TABLE {t} ENABLE TRIGGER USER")
                    print(f"  [trig] ENABLE USER on {t}")

                # 2f. 카운트 대조
                print()
                print("=" * 70)
                print("3. 행 수 대조 (dev vs prod 같은 트랜잭션 내부)")
                print("=" * 70)
                all_ok = True
                for t in DATA_TABLES:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    prod_n = cur.fetchone()[0]
                    _, rows = table_data[t]
                    dev_n = len(rows)
                    mark = "OK" if prod_n == dev_n else "MISMATCH"
                    print(f"  [{mark}] {t:42s} dev={dev_n:4d}  prod={prod_n:4d}")
                    if prod_n != dev_n:
                        all_ok = False

                # 시퀀스 검증
                print()
                for seq in SEQUENCES:
                    cur.execute(f"SELECT last_value FROM {seq}")
                    pv = cur.fetchone()[0]
                    dv = seq_values[seq]
                    mark = "OK" if pv == dv else "MISMATCH"
                    print(f"  [{mark}] {seq:50s} dev={dv}  prod={pv}")
                    if pv != dv:
                        all_ok = False

            if all_ok:
                pc.commit()
                print()
                print("=" * 70)
                print("COMMITTED — prod 동기화 완료")
                print("=" * 70)
                return 0
            else:
                pc.rollback()
                print()
                print("=" * 70)
                print("ROLLED BACK — count/sequence 불일치")
                print("=" * 70)
                return 2
        except Exception as e:
            pc.rollback()
            print()
            print("=" * 70)
            print(f"ROLLED BACK on exception: {type(e).__name__}: {e}")
            print("=" * 70)
            raise


if __name__ == "__main__":
    raise SystemExit(main())
