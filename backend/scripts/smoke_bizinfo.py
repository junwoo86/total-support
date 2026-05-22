"""BIZINFO 1페이지 실 수집 스모크 테스트.

실행: `python scripts/smoke_bizinfo.py`

목적:
- 실제 bizinfo.go.kr 1페이지 호출 (15건 이하)
- BIZINFO 스크래퍼 전체 파이프라인 (목록→상세→sanitize→파서→매처→upsert) 검증
- tb_grant_collection_runs 헬스 row + tb_grant_system_logs 적재 확인
- 최대 5건만 상세 fetch (테스트 부하 최소화)
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
from total_support.scrapers.bizinfo import BizinfoScraper  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("BIZINFO 스모크 — 1페이지만 (MAX_PAGES=1, 최대 5건 상세)")
    print("=" * 60)

    scraper = BizinfoScraper()
    scraper.MAX_PAGES = 1  # 1페이지로 제한

    # MAX_PAGES=1이지만, 페이지 안에서 신규 5건만 처리하도록 wrap
    original_process_page = scraper._process_page

    def limited_process_page(items, kw_specs, kw_version, result):
        return original_process_page(items[:5], kw_specs, kw_version, result)

    scraper._process_page = limited_process_page  # type: ignore[method-assign]

    try:
        result = scraper.run(trigger_kind="MANUAL", triggered_by="smoke@dev")
    finally:
        scraper.close()

    print()
    print(f"신규 적재: {result.new_records}건")
    print(f"갱신    : {result.updated_records}건")
    print(f"페이지  : {result.pages_visited}")
    print(f"Early Break: {result.early_break_reason}")
    if result.warnings:
        print(f"경고     : {len(result.warnings)}건")
        for w in result.warnings[:3]:
            print(f"  - {w}")

    # DB 확인
    print()
    print("=" * 60)
    print("DB 상태 확인")
    print("=" * 60)
    with engine.connect() as c:
        run = c.execute(
            text(
                "SELECT id, status, new_records, updated_records, pages_visited, "
                "early_break_reason, duration_ms, error_message "
                "FROM tb_grant_collection_runs "
                "WHERE source_site='BIZINFO' "
                "ORDER BY id DESC LIMIT 1"
            )
        ).first()
        print(f"run #{run.id}: status={run.status}, new={run.new_records}, "
              f"updated={run.updated_records}, pages={run.pages_visited}, "
              f"break={run.early_break_reason}, ms={run.duration_ms}")
        if run.error_message:
            print(f"  error: {run.error_message[:200]}")

        # 적재된 posting 일부
        rows = c.execute(
            text(
                "SELECT id, source_id, title, posting_status, ai_suitability, "
                "assigned_fields, start_date, end_date, raw_period "
                "FROM tb_grant_postings WHERE source_site='BIZINFO' "
                "ORDER BY first_seen_at DESC LIMIT 5"
            )
        ).all()
        print()
        print(f"최근 BIZINFO 공고 {len(rows)}건:")
        for r in rows:
            tag = "🔥" if r.ai_suitability == "HIGH" else "  "
            print(f"  {tag} [{r.source_id}] {r.title[:55]}")
            print(f"      상태={r.posting_status}  적합={r.ai_suitability}  분야={r.assigned_fields or '—'}")
            print(f"      접수={r.raw_period or '—'}  ({r.start_date} ~ {r.end_date})")

        # 시스템 로그
        logs = c.execute(
            text(
                "SELECT level, category, message FROM tb_grant_system_logs "
                "WHERE source_site='BIZINFO' "
                "ORDER BY created_at DESC LIMIT 5"
            )
        ).all()
        print()
        print(f"BIZINFO 시스템 로그 {len(logs)}건:")
        for log in logs:
            print(f"  [{log.level}] {log.category}: {log.message[:90]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
