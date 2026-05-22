"""키워드 백필 잡 — PRD §8.2 · §11.9.

트리거: tb_grant_domains / tb_grant_keywords INSERT/UPDATE/DELETE 후
       tb_grant_keyword_version_seq가 증가하면 Celery enqueue.
작업: screened_with_version < latest_keyword_version 인 posting을
     배치 처리하여 §3.3 매칭 재실행 후 assigned_fields/ai_suitability/
     screened_with_version 갱신.

부하 제어 (§11.9):
- 1,000행 배치 + 100ms sleep
- 운영시간(09-18 KST) 자동 throttle: 5,000행 + 1초 sleep
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from typing import Any

from sqlalchemy import select, text, update

from total_support.db import (
    GrantPosting,
    KEYWORD_VERSION_SEQ_NAME,
    SessionLocal,
)
from total_support.observability.logger import LogCategory, LogLevel, log_event
from total_support.scrapers.base import _load_keyword_specs
from total_support.screening import screen


def _strip_html(html: str) -> str:
    if not html:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()


def _is_business_hours() -> bool:
    """09–18시 KST 사이면 True."""
    from total_support.db.tz import SEOUL_TZ
    now = datetime.now(SEOUL_TZ)
    return 9 <= now.hour < 18


def run_backfill() -> dict[str, Any]:
    """백필 메인 루프 — 한 번에 latest version까지 처리하고 종료."""
    with SessionLocal() as db:
        latest_version = int(
            db.execute(text(f"SELECT last_value FROM {KEYWORD_VERSION_SEQ_NAME}")).scalar() or 0
        )
        kw_specs = _load_keyword_specs(db)

    if not kw_specs:
        return {"scanned": 0, "updated": 0, "version": latest_version, "note": "no_keywords"}

    batch_size = 5000 if _is_business_hours() else 1000
    sleep_s = 1.0 if _is_business_hours() else 0.1

    total_scanned = 0
    total_updated = 0

    while True:
        with SessionLocal() as db:
            ids = list(
                db.execute(
                    select(GrantPosting.id)
                    .where(GrantPosting.screened_with_version < latest_version)
                    .limit(batch_size)
                ).scalars()
            )
            if not ids:
                break

            postings = list(
                db.execute(
                    select(GrantPosting).where(GrantPosting.id.in_(ids))
                ).scalars()
            )

            updates: list[dict[str, Any]] = []
            for p in postings:
                text_corpus = (p.title or "") + "\n" + _strip_html(p.content_html or "")
                result = screen(text_corpus, kw_specs)
                old_fields = p.assigned_fields or ""
                new_fields = result.assigned_fields or ""
                changed = (old_fields != new_fields) or (p.ai_suitability != result.ai_suitability)
                updates.append(
                    {
                        "id": p.id,
                        "assigned_fields": new_fields or None,
                        "ai_suitability": result.ai_suitability,
                        "screened_with_version": latest_version,
                        "changed": changed,
                    }
                )

            # 한 번에 bulk update (versions만 올리는 케이스도 포함)
            for u in updates:
                db.execute(
                    update(GrantPosting)
                    .where(GrantPosting.id == u["id"])
                    .values(
                        assigned_fields=u["assigned_fields"],
                        ai_suitability=u["ai_suitability"],
                        screened_with_version=u["screened_with_version"],
                    )
                )
            total_scanned += len(ids)
            total_updated += sum(1 for u in updates if u["changed"])

            log_event(
                db,
                LogLevel.INFO,
                LogCategory.BACKFILL,
                f"백필 배치 완료 — {len(ids)}건 스캔, {sum(1 for u in updates if u['changed'])}건 갱신, "
                f"누적 {total_scanned}/{total_updated}, target_version=v{latest_version}",
                payload={
                    "batch_size": len(ids),
                    "version": latest_version,
                    "business_hours": _is_business_hours(),
                },
            )
            db.commit()

        time.sleep(sleep_s)

    return {
        "scanned": total_scanned,
        "updated": total_updated,
        "version": latest_version,
    }
