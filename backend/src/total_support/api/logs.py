"""System logs 라우터 — PRD §9 · §8.1."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import SystemLogOut
from total_support.db import GrantSystemLog

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[SystemLogOut])
def list_logs(
    db: Annotated[Session, Depends(get_db)],
    level: str | None = Query(default=None),
    category: str | None = Query(default=None),
    site: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[GrantSystemLog]:
    stmt = (
        select(GrantSystemLog)
        .order_by(desc(GrantSystemLog.created_at))
        .limit(limit)
    )
    if level:
        stmt = stmt.where(GrantSystemLog.level == level)
    if category:
        stmt = stmt.where(GrantSystemLog.category == category)
    if site:
        stmt = stmt.where(GrantSystemLog.source_site == site)
    return list(db.execute(stmt).scalars())
