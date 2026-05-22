"""Collection 라우터 — PRD §9 (run · runs · health)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import (
    CollectionRunOut,
    HealthCard,
    HealthResponse,
    RunTrigger,
    RunTriggerResponse,
)
from total_support.db import GrantCollectionRun
from total_support.db.tz import SEOUL_TZ

router = APIRouter(prefix="/collection", tags=["collection"])


# --- POST /api/grant/collection/run -------------------------
@router.post("/run", response_model=RunTriggerResponse, status_code=202)
def trigger_run(
    body: RunTrigger,
    db: Annotated[Session, Depends(get_db)],
) -> RunTriggerResponse:
    """수동 트리거 — Celery 워커로 enqueue.

    PRD §2.4.4: 같은 사이트의 이전 잡이 RUNNING이면 409 거부.
    (advisory_lock은 워커 측에서 §11.7 정책에 따라 한 번 더 보호)
    """
    # 중복 실행 방지
    existing = db.execute(
        select(GrantCollectionRun.id)
        .where(
            GrantCollectionRun.source_site == body.site,
            GrantCollectionRun.status == "RUNNING",
        )
        .limit(1)
    ).scalar()
    if existing:
        raise HTTPException(
            409,
            f"{body.site} 수집 잡이 이미 실행 중입니다 (run #{existing})",
        )

    # In-process 동시 실행 방지 추가 검사 (DB RUNNING과 별개)
    from total_support.jobs import inproc
    if inproc.is_running(body.site) is not None:
        raise HTTPException(
            409, f"{body.site} in-process 잡이 이미 실행 중입니다 (잠시 후 재시도)"
        )

    # Broker 사전 ping — Redis가 있으면 Celery, 없으면 in-process fallback.
    job_id: str
    runner: str
    try:
        import redis
        from total_support.config import get_settings
        s = get_settings()
        r = redis.from_url(s.celery_broker_url, socket_connect_timeout=1, socket_timeout=1)
        r.ping()
        # Redis OK → Celery 사용
        from total_support.jobs.tasks import scrape_site
        async_result = scrape_site.delay(body.site, trigger_kind="MANUAL", triggered_by="api")
        job_id = async_result.id
        runner = "celery"
    except Exception:  # noqa: BLE001
        # Redis/Celery 사용 불가 → in-process thread runner로 fallback.
        # dev/단일팀 환경에선 충분히 안정적.
        try:
            job_id = inproc.trigger(
                body.site, trigger_kind="MANUAL", triggered_by="api"
            )
            runner = "inproc"
        except RuntimeError as e:
            raise HTTPException(409, str(e)) from e
        except Exception as e:  # noqa: BLE001
            raise HTTPException(
                503, f"잡 디스패치 실패: {type(e).__name__}: {e}"
            ) from e

    return RunTriggerResponse(
        job_id=job_id,
        site=body.site,
        started_at=datetime.now(),
        message=f"{body.site} 수집 시작 (runner={runner}, job {job_id})",
    )


# --- GET /api/grant/collection/runs?site=...&days=30 --------
@router.get("/runs", response_model=list[CollectionRunOut])
def list_runs(
    db: Annotated[Session, Depends(get_db)],
    site: str | None = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[GrantCollectionRun]:
    since = datetime.now(SEOUL_TZ) - timedelta(days=days)
    stmt = (
        select(GrantCollectionRun)
        .where(GrantCollectionRun.started_at >= since)
        .order_by(desc(GrantCollectionRun.started_at))
        .limit(limit)
    )
    if site:
        stmt = stmt.where(GrantCollectionRun.source_site == site)
    return list(db.execute(stmt).scalars())


# --- GET /api/grant/collection/health -----------------------
@router.get("/health", response_model=HealthResponse)
def health(db: Annotated[Session, Depends(get_db)]) -> HealthResponse:
    """사이트별 헬스 카드 (PRD §2.4.3)."""
    now = datetime.now(SEOUL_TZ)
    cards: list[HealthCard] = []
    for site in ("BIZINFO", "IRIS", "SBA"):
        latest = db.execute(
            select(GrantCollectionRun)
            .where(GrantCollectionRun.source_site == site)
            .order_by(desc(GrantCollectionRun.started_at))
            .limit(1)
        ).scalar()
        last_ok = db.execute(
            select(GrantCollectionRun)
            .where(
                GrantCollectionRun.source_site == site,
                GrantCollectionRun.status == "OK",
            )
            .order_by(desc(GrantCollectionRun.started_at))
            .limit(1)
        ).scalar()

        status = latest.status if latest else "OK"
        last_ok_at = last_ok.finished_at or last_ok.started_at if last_ok else None
        is_stale = False
        if last_ok_at is not None:
            delta = now - last_ok_at
            is_stale = delta >= timedelta(hours=36)
        elif latest is not None:
            is_stale = True

        cards.append(
            HealthCard(
                source_site=site,
                status=status,
                latest_run=CollectionRunOut.model_validate(latest) if latest else None,
                last_ok_at=last_ok_at,
                is_stale=is_stale,
            )
        )
    return HealthResponse(cards=cards, server_time=now)
