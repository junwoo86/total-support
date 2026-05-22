"""Domains 라우터 — HTTP 입출력만 담당.

비즈니스 로직(쿼리/검증/도메인 예외)은 `services/domains.py` 로 위임.
서비스가 raise 하는 `NotFoundError` / `DuplicateError` 는 main.py 의
exception_handler 가 404/409 로 변환한다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import DomainCreate, DomainOut, DomainPatch
from total_support.db import GrantDomain
from total_support.services import domains as svc

router = APIRouter(prefix="/domains", tags=["domains"])


@router.get("", response_model=list[DomainOut])
def list_domains(
    db: Annotated[Session, Depends(get_db)],
    include_disabled: bool = Query(default=True),
) -> list[GrantDomain]:
    return svc.list_all(db, include_disabled=include_disabled)


@router.post("", response_model=DomainOut, status_code=201)
def create_domain(
    body: DomainCreate,
    db: Annotated[Session, Depends(get_db)],
) -> GrantDomain:
    return svc.create(db, body)


@router.patch("/{domain_id}", response_model=DomainOut)
def patch_domain(
    domain_id: int,
    body: DomainPatch,
    db: Annotated[Session, Depends(get_db)],
) -> GrantDomain:
    return svc.patch(db, domain_id, body)


@router.delete("/{domain_id}", status_code=204)
def delete_domain(
    domain_id: int,
    db: Annotated[Session, Depends(get_db)],
    hard: bool = Query(default=False, description="True면 영구 삭제 (자식 키워드 CASCADE)"),
) -> None:
    svc.delete(db, domain_id, hard=hard)
