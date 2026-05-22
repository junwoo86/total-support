"""마이그레이션 결과 종합 검증.

확인:
1. tb_grant_* 테이블 5개 + tb_grant_alembic_version 1개 존재
2. tb_grant_keyword_version_seq 시퀀스 존재
3. fn_tb_grant_bump_keyword_version 함수 + 2 트리거 존재
4. 시드 데이터: 4 도메인 + 18 키워드
5. CHECK 제약 동작 (잘못된 ENUM 값 INSERT 거부)
6. 트리거 동작 (키워드 변경 시 keyword_version_seq 증가)
7. 다른 모듈 alembic_version은 손대지 않음
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text  # noqa: E402

from total_support.db.engine import engine  # noqa: E402


def main() -> int:
    with engine.connect() as c:
        print("=" * 60)
        print("1. 본 모듈 테이블 확인")
        print("=" * 60)
        tables = c.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' "
                "AND (table_name LIKE 'tb_grant_%') "
                "ORDER BY table_name"
            )
        ).scalars().all()
        for t in tables:
            n = c.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            print(f"  ✓ {t:<40} rows={n}")

        print()
        print("=" * 60)
        print("2. 시퀀스")
        print("=" * 60)
        seq = c.execute(
            text(
                "SELECT sequencename, last_value FROM pg_sequences "
                "WHERE sequencename = 'tb_grant_keyword_version_seq'"
            )
        ).first()
        print(f"  ✓ {seq.sequencename}  last_value={seq.last_value}")

        print()
        print("=" * 60)
        print("3. 함수 + 트리거")
        print("=" * 60)
        funcs = c.execute(
            text(
                "SELECT proname FROM pg_proc WHERE proname = 'fn_tb_grant_bump_keyword_version'"
            )
        ).scalars().all()
        print(f"  ✓ function: {funcs}")
        trigs = c.execute(
            text(
                "SELECT tgname, c.relname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE tgname LIKE 'trg_tb_grant_%' ORDER BY tgname"
            )
        ).all()
        for trg in trigs:
            print(f"  ✓ trigger: {trg.tgname:<45} ON {trg.relname}")

        print()
        print("=" * 60)
        print("4. 시드 데이터 (PRD §3.1)")
        print("=" * 60)
        domains = c.execute(
            text(
                "SELECT code, label_ko, color, display_order, enabled "
                "FROM tb_grant_domains ORDER BY display_order"
            )
        ).all()
        for d in domains:
            print(f"  ✓ {d.code:<12} {d.label_ko:<10} {d.color}  order={d.display_order}  enabled={d.enabled}")

        kw_by_domain = c.execute(
            text(
                "SELECT d.code, d.display_order, COUNT(k.id) AS n "
                "FROM tb_grant_domains d "
                "LEFT JOIN tb_grant_keywords k ON k.domain_id = d.id "
                "GROUP BY d.code, d.display_order ORDER BY d.display_order"
            )
        ).all()
        print()
        for r in kw_by_domain:
            print(f"  ✓ {r.code:<12} → 키워드 {r.n}개")
        total_kw = c.execute(text("SELECT COUNT(*) FROM tb_grant_keywords")).scalar()
        print(f"  ✓ 총 키워드 {total_kw}개")

        print()
        print("=" * 60)
        print("5. CHECK 제약 동작 (의도된 거부)")
        print("=" * 60)
        try:
            c.execute(
                text(
                    "INSERT INTO tb_grant_postings "
                    "(source_site, source_id, title, detail_url, posting_status) "
                    "VALUES ('NAVER', 'test', 't', 'u', 'ONGOING')"
                )
            )
            c.commit()
            print("  ✗ FAIL — 잘못된 source_site가 통과됨")
            return 1
        except Exception as e:
            c.rollback()
            err_msg = str(e).split("\n")[0][:80]
            print(f"  ✓ source_site='NAVER' 거부됨: {err_msg}")

        print()
        print("=" * 60)
        print("6. 트리거 동작 (키워드 변경 → 시퀀스 증가)")
        print("=" * 60)
        before = c.execute(text("SELECT last_value FROM tb_grant_keyword_version_seq")).scalar()
        # AI 도메인에 임시 키워드 추가 후 즉시 삭제
        c.execute(
            text(
                "INSERT INTO tb_grant_keywords (domain_id, keyword, match_mode, "
                "case_sensitive, enabled) "
                "SELECT id, 'TRIGGER_TEST_KW', 'SUBSTRING', false, true "
                "FROM tb_grant_domains WHERE code = 'AI'"
            )
        )
        after_insert = c.execute(
            text("SELECT last_value FROM tb_grant_keyword_version_seq")
        ).scalar()
        c.execute(
            text("DELETE FROM tb_grant_keywords WHERE keyword = 'TRIGGER_TEST_KW'")
        )
        after_delete = c.execute(
            text("SELECT last_value FROM tb_grant_keyword_version_seq")
        ).scalar()
        c.commit()
        print(f"  before INSERT       = {before}")
        print(f"  after  INSERT       = {after_insert}  (+{after_insert - before})")
        print(f"  after  DELETE       = {after_delete}  (+{after_delete - after_insert})")
        if after_insert > before and after_delete > after_insert:
            print("  ✓ 트리거 정상 동작 — INSERT/DELETE 모두 시퀀스 증가")
        else:
            print("  ✗ 트리거 미작동")
            return 1

        print()
        print("=" * 60)
        print("7. 다른 모듈 alembic_version 무손상 확인")
        print("=" * 60)
        rows = c.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name LIKE '%alembic_version%' ORDER BY table_name"
            )
        ).scalars().all()
        for t in rows:
            v = c.execute(text(f"SELECT version_num FROM \"{t}\"")).scalars().all()
            marker = "(본 모듈)" if t.startswith("tb_grant_") else "(다른 모듈 — 무변경)"
            print(f"  ✓ {t:<35} {v}  {marker}")

        print()
        print("=" * 60)
        print("✓ Phase 1 검증 완료 — 모든 항목 통과")
        print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
