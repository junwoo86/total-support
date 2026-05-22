"""Celery 태스크 — 수집 · 백필.

PRD §11.7: advisory_lock 네임스페이싱.
- 모듈 prefix 841
- 사이트별 잡 코드: BIZINFO=001, IRIS=002, SBA=003
- 백필 잡 코드: 100
"""

from __future__ import annotations

from typing import Any

from celery.utils.log import get_task_logger
from sqlalchemy import text

from total_support.db import SessionLocal
from total_support.jobs.celery_app import celery_app
from total_support.observability.logger import LogCategory, LogLevel, log_event

logger = get_task_logger(__name__)


# PRD §11.7 advisory lock 네임스페이스
SITE_LOCK_KEY = {
    "BIZINFO": (841, 1),
    "IRIS":    (841, 2),
    "SBA":     (841, 3),
}
BACKFILL_LOCK_KEY = (841, 100)


@celery_app.task(name="total_support.jobs.tasks.scrape_site", bind=True)
def scrape_site(
    self,
    site: str,
    *,
    trigger_kind: str = "SCHEDULE",
    triggered_by: str = "system",
) -> dict[str, Any]:
    """단일 사이트 수집 — PRD §7 시퀀스.

    advisory_lock으로 같은 사이트 동시 실행을 차단한다. 잡 큐 중복 dispatch
    시에도 안전.
    """
    if site not in SITE_LOCK_KEY:
        raise ValueError(f"알 수 없는 site: {site}")

    lock_key = SITE_LOCK_KEY[site]

    # advisory lock 시도 (non-blocking)
    with SessionLocal() as db:
        got = db.execute(
            text("SELECT pg_try_advisory_lock(:a, :b)").bindparams(
                a=lock_key[0], b=lock_key[1]
            )
        ).scalar()
        if not got:
            log_event(
                db,
                LogLevel.WARN,
                LogCategory.SCRAPER,
                f"{site} advisory lock 획득 실패 — 이미 다른 워커가 실행 중",
                source_site=site,
                payload={"lock_key": list(lock_key), "task_id": self.request.id},
            )
            db.commit()
            return {"site": site, "skipped": True, "reason": "lock_busy"}

    try:
        from total_support.scrapers.bizinfo import BizinfoScraper
        from total_support.scrapers.iris import IrisScraper
        from total_support.scrapers.sba import SbaScraper

        scraper_cls: dict[str, Any] = {
            "BIZINFO": BizinfoScraper,
            "IRIS": IrisScraper,
            "SBA": SbaScraper,
        }[site]

        scraper = scraper_cls()
        try:
            result = scraper.run(trigger_kind=trigger_kind, triggered_by=triggered_by)
        finally:
            scraper.close()

        return {
            "site": site,
            "new": result.new_records,
            "updated": result.updated_records,
            "pages": result.pages_visited,
            "break": result.early_break_reason,
            "warnings": result.warnings[:5],
        }
    finally:
        # 락 해제
        with SessionLocal() as db:
            db.execute(
                text("SELECT pg_advisory_unlock(:a, :b)").bindparams(
                    a=lock_key[0], b=lock_key[1]
                )
            )
            db.commit()


@celery_app.task(name="total_support.jobs.tasks.run_backfill", bind=True)
def run_backfill(self) -> dict[str, Any]:
    """키워드 백필 잡 — PRD §11.9.

    PRD §11.9: 1,000행 배치 + 배치 사이 100ms sleep.
    운영 시간대(09–18시)에 시작되면 5,000행 + 1초 sleep.
    동시 1개만 (advisory lock §11.7).
    """
    from total_support.screening.backfill import run_backfill as _run

    with SessionLocal() as db:
        got = db.execute(
            text("SELECT pg_try_advisory_lock(:a, :b)").bindparams(
                a=BACKFILL_LOCK_KEY[0], b=BACKFILL_LOCK_KEY[1]
            )
        ).scalar()
        if not got:
            log_event(
                db,
                LogLevel.INFO,
                LogCategory.BACKFILL,
                "백필 잡 lock busy — 기존 잡이 진행 중 (자동 흡수)",
                payload={"task_id": self.request.id},
            )
            db.commit()
            return {"skipped": True, "reason": "lock_busy"}

    try:
        return _run()
    finally:
        with SessionLocal() as db:
            db.execute(
                text("SELECT pg_advisory_unlock(:a, :b)").bindparams(
                    a=BACKFILL_LOCK_KEY[0], b=BACKFILL_LOCK_KEY[1]
                )
            )
            db.commit()


# ============================================================
# G7 + G8 · stale 감지 + 연속 WARN 격상 알림 (PRD §8.3)
# ============================================================
@celery_app.task(name="total_support.jobs.tasks.check_health_alerts")
def check_health_alerts() -> dict[str, Any]:
    """매 시간 실행 — 36h stale + 연속 2회 WARN 검출 시 Slack 알림.

    PRD §8.3:
    - 36시간 이상 OK 기록 없음 → 적색 배너 + 알림
    - 같은 사이트 연속 2회 WARN → FAIL로 격상 알림
    """
    from datetime import datetime, timedelta

    from sqlalchemy import desc, select

    from total_support.db import GrantCollectionRun
    from total_support.db.tz import SEOUL_TZ
    from total_support.observability.slack import notify

    now = datetime.now(SEOUL_TZ)
    alerts: list[dict[str, Any]] = []

    with SessionLocal() as db:
        for site in ("BIZINFO", "IRIS", "SBA"):
            last_ok = db.execute(
                select(GrantCollectionRun)
                .where(
                    GrantCollectionRun.source_site == site,
                    GrantCollectionRun.status == "OK",
                )
                .order_by(desc(GrantCollectionRun.started_at))
                .limit(1)
            ).scalar()

            recent = list(
                db.execute(
                    select(GrantCollectionRun)
                    .where(GrantCollectionRun.source_site == site)
                    .order_by(desc(GrantCollectionRun.started_at))
                    .limit(2)
                ).scalars()
            )

            # 36시간 stale (PRD §8.3)
            if last_ok is not None:
                ref = last_ok.finished_at or last_ok.started_at
                if ref.tzinfo is None:
                    ref = ref.replace(tzinfo=SEOUL_TZ)
                if (now - ref) >= timedelta(hours=36):
                    msg = f"{site} 36시간 이상 정상 수집 없음 — 마지막 OK {ref}"
                    log_event(db, LogLevel.WARN, LogCategory.SCRAPER, msg, source_site=site)
                    if notify(msg, level="ERROR"):
                        alerts.append({"site": site, "kind": "STALE_36H"})

            # 연속 2회 WARN → 격상
            if (
                len(recent) >= 2
                and recent[0].status == "WARN"
                and recent[1].status == "WARN"
            ):
                msg = f"{site} 연속 2회 WARN — FAIL 격상 알림"
                log_event(db, LogLevel.ERROR, LogCategory.SCRAPER, msg, source_site=site)
                if notify(msg, level="ERROR"):
                    alerts.append({"site": site, "kind": "WARN_X2"})

        db.commit()

    return {"alerts": alerts, "checked_at": now.isoformat()}
