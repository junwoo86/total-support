"""SQLAlchemy engine + session factory.

PRD §11.8: 모듈 단위 statement_timeout만 connection-level로 설정한다.
서버 전역(`ALTER SYSTEM`)이나 DB(`ALTER DATABASE`) 설정은 변경하지 않는다.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from total_support.config import get_settings


def _build_engine() -> Engine:
    s = get_settings()
    return create_engine(
        s.effective_database_url,
        # 연결 단위 statement_timeout (서버/DB 전역 설정 변경 아님)
        connect_args={
            "options": f"-c statement_timeout={s.db_statement_timeout_ms}",
        },
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        # PRD §11.5: 우리 트리거 함수는 자기 모듈 외 부작용을 일으키지 않음.
        # Echo는 development에서만 켜고 싶을 때 켤 것 (지금은 끔).
        echo=False,
        future=True,
    )


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency · 컨텍스트 매니저 양쪽에서 사용 가능."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
