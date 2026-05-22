"""Domains 라우터 — PRD §9 / §5.5."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import DomainCreate, DomainOut, DomainPatch
from total_support.db import GrantDomain

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("", response_model=list[DomainOut])
def list_domains(
    db: Annotated[Session, Depends(get_db)],
    include_disabled: bool = Query(default=True),
) -> list[GrantDomain]:
    stmt = select(GrantDomain).order_by(GrantDomain.display_order.asc().nullslast(), GrantDomain.id)
    if not include_disabled:
        stmt = stmt.where(GrantDomain.enabled.is_(True))
    return list(db.execute(stmt).scalars())


@router.post("", response_model=DomainOut, status_code=201)
def create_domain(
    body: DomainCreate,
    db: Annotated[Session, Depends(get_db)],
) -> GrantDomain:
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
        raise HTTPException(409, f"code 중복 또는 제약 위반: {e.orig}") from e
    db.refresh(row)
    return row


@router.patch("/{domain_id}", response_model=DomainOut)
def patch_domain(
    domain_id: int,
    body: DomainPatch,
    db: Annotated[Session, Depends(get_db)],
) -> GrantDomain:
    row = db.get(GrantDomain, domain_id)
    if not row:
        raise HTTPException(404, "분야를 찾을 수 없습니다")
    payload = body.model_dump(exclude_unset=True)
    for k, v in payload.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{domain_id}", status_code=204)
def delete_domain(
    domain_id: int,
    db: Annotated[Session, Depends(get_db)],
    hard: bool = Query(default=False, description="True면 영구 삭제 (자식 키워드 CASCADE)"),
) -> None:
    """PRD §5.5.2: 기본은 soft delete(enabled=False). hard=True일 때만 실 DELETE."""
    row = db.get(GrantDomain, domain_id)
    if not row:
        raise HTTPException(404, "분야를 찾을 수 없습니다")
    if hard:
        db.delete(row)
    else:
        row.enabled = False
    db.commit()
