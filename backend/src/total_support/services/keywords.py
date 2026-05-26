"""Keywords 서비스 — `tb_grant_keywords` CRUD + preview.

PRD §5.5.3: 매처 4모드(WORD_BOUNDARY / EXACT_HANGUL / SUBSTRING / REGEX)
+ negative_context 좌우 30자 윈도우. REGEX 모드만 컴파일 사전 검증.

CRUD 후처리 — 키워드 정책이 바뀌면 keyword_version_seq 트리거(DB 측)가
시퀀스를 +1 하고, 본 모듈이 백그라운드 스레드로 screening backfill 을
즉시 실행한다 (회사 지침 backfill 패턴과 동일 — 빈번 호출 시 lock 으로
중복 방지). 매칭은 순수 Python 정규식이라 800+ 공고도 수 초 안에 끝남.
"""

from __future__ import annotations

import logging
import re
import threading

from sqlalchemy import select
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

from total_support.api.schemas import (
    KeywordCreate,
    KeywordPatch,
    KeywordPreviewMatch,
    KeywordPreviewRequest,
    KeywordPreviewResponse,
)
from total_support.db import GrantDomain, GrantKeyword, GrantPosting
from total_support.screening import KeywordSpec, screen
from total_support.screening.matcher import build_pattern
from total_support.services.exceptions import InvalidPatternError, NotFoundError


# ============================================================
# Screening backfill 자동 트리거 — keyword/domain CRUD 후처리
# ============================================================
_BACKFILL_LOCK = threading.Lock()
_BACKFILL_THREAD: threading.Thread | None = None


def trigger_screening_backfill_async() -> None:
    """screening/backfill.run_backfill() 을 데몬 스레드로 실행.

    이미 백필이 도는 중이면 skip — 그 백필이 끝나기 전에 새 키워드 정책이
    들어와도 어차피 run_backfill 이 latest_version 까지 한 번에 처리하므로
    추가 트리거는 불필요.
    """
    global _BACKFILL_THREAD
    with _BACKFILL_LOCK:
        if _BACKFILL_THREAD is not None and _BACKFILL_THREAD.is_alive():
            logger.info("screening backfill already running — skip new trigger")
            return
        t = threading.Thread(
            target=_run_backfill_safely,
            daemon=True,
            name="screening-backfill",
        )
        _BACKFILL_THREAD = t
        t.start()


def _run_backfill_safely() -> None:
    from total_support.screening.backfill import run_backfill
    try:
        result = run_backfill()
        logger.info("screening backfill done: %s", result)
    except Exception as e:  # noqa: BLE001
        logger.warning("screening backfill failed: %s", e)


# ============================================================
# CRUD
# ============================================================
def list_for_domain(db: Session, domain_id: int) -> list[GrantKeyword]:
    if not db.get(GrantDomain, domain_id):
        raise NotFoundError("분야를 찾을 수 없습니다")
    return list(
        db.execute(
            select(GrantKeyword)
            .where(GrantKeyword.domain_id == domain_id)
            .order_by(GrantKeyword.id)
        ).scalars()
    )


def create(db: Session, domain_id: int, body: KeywordCreate) -> GrantKeyword:
    if not db.get(GrantDomain, domain_id):
        raise NotFoundError("분야를 찾을 수 없습니다")
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
    trigger_screening_backfill_async()
    return row


def patch(
    db: Session, domain_id: int, keyword_id: int, body: KeywordPatch
) -> GrantKeyword:
    row = db.get(GrantKeyword, keyword_id)
    if not row or row.domain_id != domain_id:
        raise NotFoundError("키워드를 찾을 수 없습니다")

    diff = body.model_dump(exclude_unset=True)
    # 모드/키워드 변경 시 REGEX 사전 검증
    new_kw = diff.get("keyword", row.keyword)
    new_mode = diff.get("match_mode", row.match_mode)
    _validate_regex_if_needed(new_kw, new_mode)

    for k, v in diff.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    trigger_screening_backfill_async()
    return row


def delete(db: Session, domain_id: int, keyword_id: int) -> None:
    row = db.get(GrantKeyword, keyword_id)
    if not row or row.domain_id != domain_id:
        raise NotFoundError("키워드를 찾을 수 없습니다")
    db.delete(row)
    db.commit()
    trigger_screening_backfill_async()


# ============================================================
# Preview (PRD §5.5.3) — 최근 100건 대조
# ============================================================
def preview(db: Session, body: KeywordPreviewRequest) -> KeywordPreviewResponse:
    _validate_regex_if_needed(body.keyword, body.match_mode)

    spec = KeywordSpec(
        keyword=body.keyword,
        match_mode=body.match_mode,
        domain_label="(preview)",
        case_sensitive=body.case_sensitive,
        negative_context=tuple(body.negative_context),
        enabled=True,
    )
    # build_pattern 으로 pre-validate (오류 시 422)
    try:
        build_pattern(spec)
    except (re.error, ValueError) as e:
        raise InvalidPatternError(f"잘못된 키워드/모드: {e}") from e

    rows = (
        db.execute(
            select(GrantPosting).order_by(GrantPosting.first_seen_at.desc()).limit(100)
        )
        .scalars()
        .all()
    )

    # 본문 노이즈(푸터·메뉴·사이드바) 가 키워드 매처에 섞이지 않도록
    # _trim_body_html 로 site 별 본문 fragment 만 추출한 뒤 매칭.
    from total_support.services.postings import _trim_body_html

    samples: list[KeywordPreviewMatch] = []
    matched_count = 0
    for p in rows:
        trimmed = _trim_body_html(p.source_site, p.content_html or "")
        text = (p.title or "") + "\n" + _strip_html(trimmed or "")
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
    return KeywordPreviewResponse(
        matched=matched_count, scanned=len(rows), samples=samples
    )


# ============================================================
# 헬퍼
# ============================================================
def _validate_regex_if_needed(keyword: str, match_mode: str) -> None:
    """REGEX 모드는 컴파일 사전 검증 (PRD §5.5.3)."""
    if match_mode != "REGEX":
        return
    try:
        re.compile(keyword)
    except re.error as e:
        raise InvalidPatternError(f"REGEX 패턴 오류: {e}") from e


def _strip_html(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
