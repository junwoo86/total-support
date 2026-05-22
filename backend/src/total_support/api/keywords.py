"""Keywords 라우터 — HTTP 입출력만 담당.

비즈니스 로직(REGEX 사전 검증, screening 호출 등)은 `services/keywords.py`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import (
    KeywordCreate,
    KeywordOut,
    KeywordPatch,
    KeywordPreviewRequest,
    KeywordPreviewResponse,
)
from total_support.db import GrantKeyword
from total_support.services import keywords as svc

router = APIRouter(prefix="/domains/{domain_id}/keywords", tags=["keywords"])


@router.get("", response_model=list[KeywordOut])
def list_keywords(
    domain_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[GrantKeyword]:
    return svc.list_for_domain(db, domain_id)


@router.post("", response_model=KeywordOut, status_code=201)
def create_keyword(
    domain_id: int,
    body: KeywordCreate,
    db: Annotated[Session, Depends(get_db)],
) -> GrantKeyword:
    return svc.create(db, domain_id, body)


@router.patch("/{keyword_id}", response_model=KeywordOut)
def patch_keyword(
    domain_id: int,
    keyword_id: int,
    body: KeywordPatch,
    db: Annotated[Session, Depends(get_db)],
) -> GrantKeyword:
    return svc.patch(db, domain_id, keyword_id, body)


@router.delete("/{keyword_id}", status_code=204)
def delete_keyword(
    domain_id: int,
    keyword_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    svc.delete(db, domain_id, keyword_id)


# --- Preview (PRD §5.5.3) -----------------------------------
# 별도 라우터: /api/grant/keywords/preview (domain_id 비종속)
preview_router = APIRouter(prefix="/keywords", tags=["keywords"])


@preview_router.post("/preview", response_model=KeywordPreviewResponse)
def preview_keyword(
    body: KeywordPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
) -> KeywordPreviewResponse:
    return svc.preview(db, body)
