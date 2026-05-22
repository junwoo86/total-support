"""Alembic 환경 — 본 모듈 한정 (PRD §11.1 · §11.10).

핵심 안전 장치:
- DSN을 `total_support.config.get_settings()`에서 가져와 .env와 일치시킨다.
- include_object 훅으로 **`tb_grant_*` 접두사 외 객체는 자동 발견에서 제외**한다.
  (실수로 다른 모듈 테이블이 마이그레이션에 끌려 들어오는 것을 차단)
- compare_type=True · compare_server_default=True로 미세 diff를 잡는다.
- 트랜잭션은 마이그레이션 단위로 분리 (additive only 원칙).
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine, pool

# --- 경로 등록 (src/ 레이아웃) -------------------------------
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from total_support.config import get_settings  # noqa: E402
from total_support.db import Base  # noqa: E402

# Alembic 설정 객체 (alembic.ini 로드)
config = context.config

# 로깅
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# DSN 주입 (offline mode에서 사용)
config.set_main_option("sqlalchemy.url", get_settings().effective_database_url)

# autogenerate 대상 메타데이터
target_metadata = Base.metadata


# --- 객체 필터 ----------------------------------------------
# PRD §11.1: 본 모듈 외 객체는 절대로 마이그레이션에 포함시키지 않는다.
_OUR_PREFIX = "tb_grant_"


def include_object(obj, name, type_, reflected, compare_to):
    """다른 모듈 테이블/인덱스가 발견되어도 무시한다."""
    if type_ == "table":
        return name.startswith(_OUR_PREFIX)
    if type_ in ("index", "unique_constraint"):
        return getattr(obj, "table", None) is not None and obj.table.name.startswith(_OUR_PREFIX)
    return True


def run_migrations_offline() -> None:
    """Offline mode — SQL 파일로만 생성."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        compare_type=True,
        compare_server_default=True,
        # PRD §11.1: 다른 모듈의 alembic_version을 침범하지 않는다.
        version_table="tb_grant_alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online mode — settings에서 직접 엔진을 만든다 (alembic.ini placeholder 우회).

    statement_timeout도 connection-level로 강제 (§11.8).
    """
    s = get_settings()
    connectable = create_engine(
        s.effective_database_url,
        poolclass=pool.NullPool,
        connect_args={
            "options": f"-c statement_timeout={s.db_statement_timeout_ms}",
        },
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            compare_type=True,
            compare_server_default=True,
            # PRD §11.1: 다른 모듈의 alembic_version을 침범하지 않는다.
            version_table="tb_grant_alembic_version",
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
