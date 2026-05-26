"""Company guideline 서비스 — 회사 적합도 평가용 시스템 프롬프트.

단일 row (id=1) 운영. 수정 시 version +1 → UNREVIEWED 공고 재평가 자동 트리거.
검토가 시작된 (NEEDS_REVIEW / IN_PROGRESS / EXCLUDED) 공고는 historical
평가값을 보존 (사용자 결정 영향 영구 기록).
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from total_support.db import GrantCompanyGuideline, GrantPosting, SessionLocal

logger = logging.getLogger(__name__)


# ============================================================
# 평가 단계에서 base.py 가 호출하는 가벼운 read 모델
# ============================================================
@dataclass(slots=True, frozen=True)
class GuidelineSnapshot:
    content_md: str
    version: int


def get_current_guideline_for_eval() -> GuidelineSnapshot | None:
    """수집 시점 평가용 — 빈 지침이거나 미존재면 None.

    Append-only 패턴: "현재" = ORDER BY version DESC LIMIT 1.
    """
    with SessionLocal() as db:
        row = _current_row(db)
        if not row or not (row.content_md or "").strip():
            return None
        return GuidelineSnapshot(content_md=row.content_md, version=row.version)


def _current_row(db: Session) -> GrantCompanyGuideline | None:
    """append-only 테이블에서 최신 row 반환."""
    return db.execute(
        select(GrantCompanyGuideline)
        .order_by(GrantCompanyGuideline.version.desc())
        .limit(1)
    ).scalar_one_or_none()


# ============================================================
# CRUD (API 라우터에서 사용)
# ============================================================
def get_current(db: Session) -> GrantCompanyGuideline:
    """현재값 = 최대 version row. 비어있으면 v1 빈 row 자동 생성."""
    row = _current_row(db)
    if row is None:
        row = GrantCompanyGuideline(content_md="", version=1)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def list_history(db: Session, *, limit: int = 50) -> list[GrantCompanyGuideline]:
    """모든 버전 히스토리 (최신 → 과거)."""
    return list(
        db.execute(
            select(GrantCompanyGuideline)
            .order_by(GrantCompanyGuideline.version.desc())
            .limit(limit)
        ).scalars()
    )


def update_content(
    db: Session, *, content_md: str, trigger_backfill: bool = True,
) -> GrantCompanyGuideline:
    """지침 본문 수정 — **새 row INSERT** (append-only, 과거 보존).

    Args:
        content_md: 새 본문. 이전 version 과 동일하면 no-op.
        trigger_backfill: True (기본) → UNREVIEWED 공고 자동 재평가 백그라운드 시작.
                          False → 새 row 만 저장하고 평가는 건드리지 않음
                          (사소한 표현 수정·오타 정정 시).
    """
    current = get_current(db)
    new_md = (content_md or "").strip()

    if new_md == (current.content_md or "").strip():
        return current  # no-op — 동일 본문이면 새 row 안 만든다

    new_row = GrantCompanyGuideline(
        content_md=new_md,
        version=current.version + 1,
        updated_at=datetime.now(timezone.utc),
    )
    db.add(new_row)
    db.commit()
    db.refresh(new_row)

    if trigger_backfill:
        # UNREVIEWED 공고 재평가는 백그라운드 스레드로 — 라우터 응답 차단 X
        _trigger_reevaluation_async(new_version=new_row.version)
    return new_row


# ============================================================
# UNREVIEWED 재평가 백필 (지침 변경 시 자동)
# ============================================================
_BACKFILL_LOCK = threading.Lock()
_BACKFILL_THREAD: threading.Thread | None = None


def _trigger_reevaluation_async(*, new_version: int) -> None:
    """UNREVIEWED 공고 전수 재평가를 별도 스레드에서 실행 (중복 방지)."""
    global _BACKFILL_THREAD
    with _BACKFILL_LOCK:
        if _BACKFILL_THREAD is not None and _BACKFILL_THREAD.is_alive():
            logger.info("guideline backfill already running — skip new trigger")
            return
        t = threading.Thread(
            target=_run_reevaluation,
            args=(new_version,),
            daemon=True,
            name=f"guideline-backfill-v{new_version}",
        )
        _BACKFILL_THREAD = t
        t.start()


def _run_reevaluation(new_version: int) -> None:
    """실제 백필 본체 — UNREVIEWED 공고들을 새 지침으로 재평가."""
    from total_support.services.evaluator import get_evaluator

    evaluator = get_evaluator()
    if evaluator is None:
        logger.info("evaluator disabled (no ADC/project) — skip backfill")
        return

    snapshot = get_current_guideline_for_eval()
    if snapshot is None or snapshot.version != new_version:
        # 지침이 또 바뀌었으면 새 트리거가 처리할 것
        return

    # 백필 대상 — UNREVIEWED 만 (사용자가 검토 시작한 건 historical 보존)
    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(
                    GrantPosting.id,
                    GrantPosting.source_site,
                    GrantPosting.title,
                    GrantPosting.content_html,
                ).where(GrantPosting.review_status == "UNREVIEWED")
            ).all()
        )

    if not rows:
        return
    logger.info("guideline backfill: re-evaluating %d UNREVIEWED postings", len(rows))

    # 동시성 절제 — 한 번에 1건씩 처리. Gemini-flash 라 큰 부담은 없고
    # 운영 DB 쪽 트랜잭션 부담을 분산한다.
    # _trim_body_html 로 raw content_html → 본문 fragment 만 추출해 노이즈
    # (푸터, 메뉴, 사이드바) 가 평가에 섞이지 않도록 한다.
    from total_support.scrapers.base import _strip_tags_for_match
    from total_support.services.postings import _trim_body_html

    updated = 0
    failed = 0
    for pid, site, title, html in rows:
        trimmed = _trim_body_html(site, html or "")
        body = _strip_tags_for_match(trimmed or "")
        result = evaluator.evaluate(
            guideline_md=snapshot.content_md,
            posting_title=title or "",
            posting_body=body,
        )
        with SessionLocal() as db:
            if result is None:
                # 3회 재시도 실패 — UI 최상단 노출용 플래그 적재
                db.execute(
                    update(GrantPosting)
                    .where(GrantPosting.id == pid)
                    .values(
                        relevance_score=None,
                        relevance_reason=None,
                        evaluated_with_guideline_version=new_version,
                        evaluation_failed=True,
                    )
                )
                failed += 1
            else:
                db.execute(
                    update(GrantPosting)
                    .where(GrantPosting.id == pid)
                    .values(
                        relevance_score=result.score,
                        relevance_reason=result.reason,
                        evaluated_with_guideline_version=new_version,
                        evaluation_failed=False,
                    )
                )
                updated += 1
            db.commit()
    logger.info(
        "guideline backfill done — updated=%d failed=%d / total=%d",
        updated, failed, len(rows),
    )
