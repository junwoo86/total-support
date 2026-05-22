"""Keywords 라우터 — PRD §9 / §5.5.3."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from total_support.api.deps import get_db
from total_support.api.schemas import (
    KeywordCreate,
    KeywordOut,
    KeywordPatch,
    KeywordPreviewMatch,
    KeywordPreviewRequest,
    KeywordPreviewResponse,
)
from total_support.db import GrantDomain, GrantKeyword, GrantPosting
from total_support.screening import KeywordSpec, screen
from total_support.screening.matcher import CONTEXT_RADIUS, build_pattern

router = APIRouter(prefix="/domains/{domain_id}/keywords", tags=["keywords"])


@router.get("", response_model=list[KeywordOut])
def list_keywords(
    domain_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> list[GrantKeyword]:
    if not db.get(GrantDomain, domain_id):
        raise HTTPException(404, "분야를 찾을 수 없습니다")
    return list(
        db.execute(
            select(GrantKeyword)
            .where(GrantKeyword.domain_id == domain_id)
            .order_by(GrantKeyword.id)
        ).scalars()
    )


@router.post("", response_model=KeywordOut, status_code=201)
def create_keyword(
    domain_id: int,
    body: KeywordCreate,
    db: Annotated[Session, Depends(get_db)],
) -> GrantKeyword:
    if not db.get(GrantDomain, domain_id):
        raise HTTPException(404, "분야를 찾을 수 없습니다")
    _validate_regex_if_needed(body.keyword, body.match_mode)

    row = GrantKeyword(
        domain_id=domain_id,
        keyword=body.keyword,
        match_mode=body.match_mode,
        case_sensitive=body.case_sensitive,
        negative_context=body.negative_context,
        enabled=body.enabled,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/{keyword_id}", response_model=KeywordOut)
def patch_keyword(
    domain_id: int,
    keyword_id: int,
    body: KeywordPatch,
    db: Annotated[Session, Depends(get_db)],
) -> GrantKeyword:
    row = db.get(GrantKeyword, keyword_id)
    if not row or row.domain_id != domain_id:
        raise HTTPException(404, "키워드를 찾을 수 없습니다")

    patch = body.model_dump(exclude_unset=True)
    new_kw = patch.get("keyword", row.keyword)
    new_mode = patch.get("match_mode", row.match_mode)
    _validate_regex_if_needed(new_kw, new_mode)

    for k, v in patch.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{keyword_id}", status_code=204)
def delete_keyword(
    domain_id: int,
    keyword_id: int,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    row = db.get(GrantKeyword, keyword_id)
    if not row or row.domain_id != domain_id:
        raise HTTPException(404, "키워드를 찾을 수 없습니다")
    db.delete(row)
    db.commit()


# --- Preview (PRD §5.5.3) -----------------------------------
# 별도 라우터: /api/grant/keywords/preview
preview_router = APIRouter(prefix="/keywords", tags=["keywords"])


@preview_router.post("/preview", response_model=KeywordPreviewResponse)
def preview_keyword(
    body: KeywordPreviewRequest,
    db: Annotated[Session, Depends(get_db)],
) -> KeywordPreviewResponse:
    """PRD §5.5.3: 최근 100건 대조 미리보기."""
    _validate_regex_if_needed(body.keyword, body.match_mode)

    spec = KeywordSpec(
        keyword=body.keyword,
        match_mode=body.match_mode,
        domain_label="(preview)",
        case_sensitive=body.case_sensitive,
        negative_context=tuple(body.negative_context),
        enabled=True,
    )
    # build_pattern으로 pre-validate (오류 시 422)
    try:
        build_pattern(spec)
    except (re.error, ValueError) as e:
        raise HTTPException(422, f"잘못된 키워드/모드: {e}") from e

    rows = (
        db.execute(
            select(GrantPosting).order_by(GrantPosting.first_seen_at.desc()).limit(100)
        )
        .scalars()
        .all()
    )

    samples: list[KeywordPreviewMatch] = []
    matched_count = 0
    for p in rows:
        text = (p.title or "") + "\n" + _strip_html(p.content_html or "")
        result = screen(text, [spec])
        if result.hits:
            matched_count += 1
            if len(samples) < 5:
                hit = result.hits[0]
                samples.append(
                    KeywordPreviewMatch(
                        posting_id=p.id,
                        title=p.title,
                        context=hit.context,
                        start=hit.start,
                        end=hit.end,
                    )
                )
    return KeywordPreviewResponse(matched=matched_count, scanned=len(rows), samples=samples)


# --- 헬퍼 ---------------------------------------------------
def _validate_regex_if_needed(keyword: str, match_mode: str) -> None:
    """REGEX 모드는 컴파일 사전 검증 (PRD §5.5.3)."""
    if match_mode != "REGEX":
        return
    try:
        re.compile(keyword)
    except re.error as e:
        raise HTTPException(422, f"REGEX 패턴 오류: {e}") from e


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
