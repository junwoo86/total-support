"""잡 큐 — Celery + Redis."""

from total_support.jobs.celery_app import celery_app

__all__ = ["celery_app"]
