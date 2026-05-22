"""tb_grant_system_logs writer — PRD §8.1.

PRD §11.5: 트리거가 다른 테이블에 쓰지 않듯, 본 모듈도 자기 system_logs
테이블에만 기록한다. 외부 모듈 로그 시스템과는 분리.

호출자 패턴:
    with SessionLocal() as db:
        log_event(db, LogLevel.WARN, LogCategory.SCRAPER, "BIZINFO 신규 0건", source_site="BIZINFO")
        db.commit()
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from total_support.db.models import GrantSystemLog


class LogLevel(StrEnum):
    """PRD §8.1: INFO / WARN / ERROR."""

    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogCategory(StrEnum):
    """PRD §8.1: PARSE_PERIOD / URL_TRUNCATED / BACKFILL / SCRAPER / API."""

    PARSE_PERIOD = "PARSE_PERIOD"
    URL_TRUNCATED = "URL_TRUNCATED"
    BACKFILL = "BACKFILL"
    SCRAPER = "SCRAPER"
    API = "API"


def log_event(
    db: Session,
    level: LogLevel | str,
    category: LogCategory | str,
    message: str,
    *,
    source_site: str | None = None,
    posting_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> GrantSystemLog:
    """system_logs에 1행 INSERT (트랜잭션은 호출자가 commit).

    Args:
        db: SQLAlchemy 세션.
        level: 로그 레벨 (LogLevel 또는 문자열).
        category: 카테고리 (LogCategory 또는 문자열).
        message: 사람이 읽을 메시지.
        source_site: 관련 사이트 (BIZINFO/IRIS/SBA), 있으면.
        posting_id: 관련 tb_grant_postings.id, 있으면.
        payload: 추가 JSON 컨텍스트.

    Returns:
        flush 직후의 GrantSystemLog (id 채워짐).
    """
    row = GrantSystemLog(
        level=str(level),
        category=str(category),
        source_site=source_site,
        posting_id=posting_id,
        message=message,
        payload=payload,
    )
    db.add(row)
    db.flush()
    return row
