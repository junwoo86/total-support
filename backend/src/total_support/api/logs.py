"""System logs 라우터 — HTTP 입출력만 담당."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import SystemLogOut
from total_support.db import GrantSystemLog
from total_support.services import logs as svc

router = APIRouter(prefix="/logs", tags=["logs"])


@router.get("", response_model=list[SystemLogOut])
def list_logs(
    db: Annotated[Session, Depends(get_db)],
    level: str | None = Query(default=None),
    category: str | None = Query(default=None),
    site: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=2000),
) -> list[GrantSystemLog]:
    return svc.list_recent(
        db, level=level, category=category, site=site, limit=limit
    )
