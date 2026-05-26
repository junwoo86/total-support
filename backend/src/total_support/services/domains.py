"""Domains 서비스 — 분야 마스터(`tb_grant_domains`) CRUD."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from total_support.api.schemas import DomainCreate, DomainPatch
from total_support.db import GrantDomain
from total_support.services.exceptions import DuplicateError, NotFoundError
from total_support.services.keywords import trigger_screening_backfill_async


def list_all(db: Session, *, include_disabled: bool = True) -> list[GrantDomain]:
    """display_order ASC NULLS LAST, id ASC 순으로 분야 목록 반환."""
    stmt = select(GrantDomain).order_by(
        GrantDomain.display_order.asc().nullslast(),
        GrantDomain.id,
    )
    if not include_disabled:
        stmt = stmt.where(GrantDomain.enabled.is_(True))
    return list(db.execute(stmt).scalars())


def create(db: Session, body: DomainCreate) -> GrantDomain:
    """새 분야 생성. code UNIQUE 위반 시 `DuplicateError`."""
    row = GrantDomain(
        code=body.code,
        label_ko=body.label_ko,
        color=body.color,
        display_order=body.display_order,
        enabled=body.enabled,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        raise DuplicateError(f"code 중복 또는 제약 위반: {e.orig}") from e
    db.refresh(row)
    trigger_screening_backfill_async()
    return row


def patch(db: Session, domain_id: int, body: DomainPatch) -> GrantDomain:
    """부분 업데이트(exclude_unset). 미존재 시 `NotFoundError`."""
    row = db.get(GrantDomain, domain_id)
    if not row:
        raise NotFoundError("분야를 찾을 수 없습니다")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    trigger_screening_backfill_async()
    return row


def delete(db: Session, domain_id: int, *, hard: bool) -> None:
    """PRD §5.5.2: 기본은 soft delete(enabled=False).

    hard=True 일 때만 실 DELETE — 자식 키워드는 FK CASCADE 로 함께 사라진다.
    """
    row = db.get(GrantDomain, domain_id)
    if not row:
        raise NotFoundError("분야를 찾을 수 없습니다")
    if hard:
        db.delete(row)
    else:
        row.enabled = False
    db.commit()
    trigger_screening_backfill_async()
