"""Company guideline 라우터 — 회사 적합도 평가용 시스템 지침.

GET /api/grant/company-guideline      → 현재 지침 (단일 row)
PUT /api/grant/company-guideline      → 지침 본문 수정 → version +1 →
                                        UNREVIEWED 공고 자동 재평가 백그라운드 트리거

비즈니스 로직은 services/guidelines.py 에 있다.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import (
    CompanyGuidelineHistoryItem,
    CompanyGuidelineOut,
    CompanyGuidelinePut,
)
from total_support.db import GrantCompanyGuideline
from total_support.services import guidelines as svc

router = APIRouter(prefix="/company-guideline", tags=["company-guideline"])


@router.get("", response_model=CompanyGuidelineOut)
def get_guideline(
    db: Annotated[Session, Depends(get_db)],
) -> GrantCompanyGuideline:
    return svc.get_current(db)


@router.put("", response_model=CompanyGuidelineOut)
def put_guideline(
    body: CompanyGuidelinePut,
    db: Annotated[Session, Depends(get_db)],
) -> GrantCompanyGuideline:
    return svc.update_content(
        db, content_md=body.content_md, trigger_backfill=body.reevaluate,
    )


@router.get("/history", response_model=list[CompanyGuidelineHistoryItem])
def get_history(
    db: Annotated[Session, Depends(get_db)],
) -> list[GrantCompanyGuideline]:
    """모든 버전 (최신 → 과거). append-only 테이블에서 그대로 조회."""
    return svc.list_history(db)
