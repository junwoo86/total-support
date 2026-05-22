"""Celery 애플리케이션 — PRD §10 · §11.7 advisory_lock.

브로커: Redis (.env의 TS_CELERY_BROKER_URL).
Beat 스케줄: 매일 04:00 KST 자동 트리거.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from total_support.config import get_settings
from total_support.db.tz import SEOUL_TZ

_settings = get_settings()

celery_app = Celery(
    "total_support",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["total_support.jobs.tasks"],
)

celery_app.conf.update(
    timezone=str(SEOUL_TZ),               # Beat 스케줄 명시 (Asia/Seoul)
    enable_utc=False,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=200,
    broker_connection_retry_on_startup=True,
)

# PRD §10: 매일 04:00 KST 자동 수집 (사이트별 staggered 시각)
celery_app.conf.beat_schedule = {
    "schedule-bizinfo-0400": {
        "task": "total_support.jobs.tasks.scrape_site",
        "schedule": crontab(hour=4, minute=3),
        "args": ("BIZINFO",),
        "kwargs": {"trigger_kind": "SCHEDULE", "triggered_by": "system"},
    },
    "schedule-iris-0407": {
        "task": "total_support.jobs.tasks.scrape_site",
        "schedule": crontab(hour=4, minute=7),
        "args": ("IRIS",),
        "kwargs": {"trigger_kind": "SCHEDULE", "triggered_by": "system"},
    },
    "schedule-sba-0409": {
        "task": "total_support.jobs.tasks.scrape_site",
        "schedule": crontab(hour=4, minute=9),
        "args": ("SBA",),
        "kwargs": {"trigger_kind": "SCHEDULE", "triggered_by": "system"},
    },
    # G7/G8: 매 시간 0분 — stale 감지 + 연속 WARN 격상
    "health-alert-hourly": {
        "task": "total_support.jobs.tasks.check_health_alerts",
        "schedule": crontab(minute=0),
    },
}


def worker_entry() -> None:
    """`ts-worker` 콘솔 스크립트."""
    celery_app.start(argv=["worker", "--loglevel=INFO"])
