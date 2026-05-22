"""실 데이터 시드 풍부화 — BIZINFO 3페이지 (최대 45건) 수집.

프론트엔드 풀스택 데모 시 5건만으론 부족하므로 1회만 수동 실행해서
DB를 채운다. 일일 04:00 자동 스케줄과 별도.
"""

from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import text  # noqa: E402

from total_support.db.engine import engine  # noqa: E402
from total_support.scrapers.bizinfo import BizinfoScraper  # noqa: E402


def main() -> int:
    print("=" * 60)
    print("BIZINFO 시드 풍부화 — 3페이지 (~45건)")
    print("=" * 60)

    scraper = BizinfoScraper()
    scraper.MAX_PAGES = 3

    try:
        result = scraper.run(trigger_kind="MANUAL", triggered_by="seed@dev")
    finally:
        scraper.close()

    print()
    print(f"신규 적재: {result.new_records}건")
    print(f"갱신    : {result.updated_records}건")
    print(f"페이지  : {result.pages_visited}")
    print(f"Early Break: {result.early_break_reason}")
    if result.warnings:
        print(f"경고     : {len(result.warnings)}건")
        for w in result.warnings[:5]:
            print(f"  - {w}")

    with engine.connect() as c:
        total = c.execute(text("SELECT COUNT(*) FROM tb_grant_postings")).scalar()
        high = c.execute(
            text("SELECT COUNT(*) FROM tb_grant_postings WHERE ai_suitability='HIGH'")
        ).scalar()
        by_site = c.execute(
            text(
                "SELECT source_site, COUNT(*) FROM tb_grant_postings "
                "GROUP BY source_site ORDER BY source_site"
            )
        ).all()
        print()
        print(f"DB 누적 공고 {total}건 (HIGH 적합 {high}건)")
        for site, n in by_site:
            print(f"  - {site}: {n}건")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
