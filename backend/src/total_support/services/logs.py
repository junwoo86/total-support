"""System logs 서비스 — `tb_grant_system_logs` 조회."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from total_support.db import GrantSystemLog


def list_recent(
    db: Session,
    *,
    level: str | None = None,
    category: str | None = None,
    site: str | None = None,
    limit: int = 200,
) -> list[GrantSystemLog]:
    """created_at DESC 순 최근 N건 — 필터 옵셔널."""
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
