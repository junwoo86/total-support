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

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from total_support.db import (
    GrantCompanyGuideline,
    GrantPosting,
    SessionLocal,
    seoul_today_expr,
)

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
# 2단 동시성 제어:
#  1) _BACKFILL_LOCK (thread)  — 같은 프로세스 내 중복 트리거 즉시 차단 (빠름)
#  2) pg advisory lock         — 여러 프로세스/워커/사용자 브라우저가 동시에
#                                요청해도 DB 수준에서 1개만 평가 실행 (cross-process)
# 지침 백필(_run_reevaluation)과 미평가 채우기(_run_fill_missing)는 둘 다 같은
# evaluator 를 쓰는 무거운 작업이므로 동일 advisory key 를 공유 — 동시 실행 금지.
_BACKFILL_LOCK = threading.Lock()
_BACKFILL_THREAD: threading.Thread | None = None

# PRD §11.7 advisory lock 네임스페이스 — 키워드 백필(841,100)과 구분해 (841,101).
_EVAL_LOCK_KEY = (841, 101)

# fill-missing 진행 상태 — 프론트 프로그레스바 폴링용.
# 단일 프로세스 가정 (advisory lock 으로 1 프로세스만 실행되므로 그 프로세스의
# 상태를 폴링). multi-worker 배포 시엔 DB 기반 progress row 로 전환 필요.
_PROGRESS_LOCK = threading.Lock()
_FILL_PROGRESS: dict = {
    "running": False,
    "total": 0,
    "processed": 0,
    "updated": 0,
    "failed": 0,
    "started_at": None,
    "finished_at": None,
}


def get_fill_progress() -> dict:
    """현재 fill-missing 진행 상태 스냅샷 (프론트 폴링)."""
    with _PROGRESS_LOCK:
        return dict(_FILL_PROGRESS)


def _set_progress(**patch) -> None:
    with _PROGRESS_LOCK:
        _FILL_PROGRESS.update(patch)


def _try_eval_advisory_lock(conn) -> bool:
    """평가 백필 전용 DB advisory lock 획득 (non-blocking). 이 conn 이 살아있는
    동안만 유지되며 conn.close() 시 자동 해제 (session-level lock)."""
    return bool(
        conn.execute(
            text("SELECT pg_try_advisory_lock(:a, :b)").bindparams(
                a=_EVAL_LOCK_KEY[0], b=_EVAL_LOCK_KEY[1]
            )
        ).scalar()
    )


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


# ============================================================
# 적합도 미평가 건 수동 재평가 (사용자 버튼)
# 대상: UNREVIEWED + 미만료 + 적합도 비어있음
#   (relevance_score IS NULL OR evaluation_failed=true)
# 검토 시작했거나(다른 status) 기한 지난 건은 제외.
# ============================================================
def _missing_eval_clause():
    """재평가 대상 조건 — 신규 미검토 탭에 보이면서 점수가 비어있는 행."""
    return (
        (GrantPosting.review_status == "UNREVIEWED")
        & (
            GrantPosting.relevance_score.is_(None)
            | (GrantPosting.evaluation_failed.is_(True))
        )
        & (
            GrantPosting.end_date.is_(None)
            | (GrantPosting.end_date >= seoul_today_expr())
        )
    )


def count_missing_eval(db: Session) -> int:
    """재평가 대상 건수 — UI 버튼 옆 숫자."""
    return int(
        db.execute(
            select(func.count()).select_from(
                select(GrantPosting.id).where(_missing_eval_clause()).subquery()
            )
        ).scalar_one()
    )


def trigger_fill_missing_async() -> dict:
    """미평가 건 재평가를 백그라운드로 시작.

    Returns: {started: bool, target_count: int, reason: str|None}
    - evaluator 비활성(ADC/지침 미설정) → started=False
    - 이미 백필 진행 중 → started=False (lock 공유)
    """
    from total_support.services.evaluator import get_evaluator

    if get_evaluator() is None:
        return {"started": False, "target_count": 0,
                "reason": "evaluator 비활성 (ADC/GCP_PROJECT 미설정)"}
    if get_current_guideline_for_eval() is None:
        return {"started": False, "target_count": 0,
                "reason": "회사 지침이 비어 있음"}

    with SessionLocal() as db:
        target = count_missing_eval(db)
    if target == 0:
        return {"started": False, "target_count": 0,
                "reason": "재평가할 미평가 건이 없습니다"}

    global _BACKFILL_THREAD
    with _BACKFILL_LOCK:
        if _BACKFILL_THREAD is not None and _BACKFILL_THREAD.is_alive():
            return {"started": False, "target_count": target,
                    "reason": "이미 재평가가 진행 중입니다"}
        t = threading.Thread(
            target=_run_fill_missing,
            daemon=True,
            name="fill-missing-eval",
        )
        _BACKFILL_THREAD = t
        t.start()
    return {"started": True, "target_count": target, "reason": None}


def _run_fill_missing() -> None:
    """미평가(UNREVIEWED+미만료+점수없음) 건을 현재 지침으로 평가.

    본문이 짧거나 비어도 evaluate(allow_short=True) 로 제목 기반 추측 평가.
    DB advisory lock 으로 다른 프로세스/워커의 동시 평가 백필을 차단.
    """
    from total_support.scrapers.base import _strip_tags_for_match
    from total_support.services.evaluator import get_evaluator
    from total_support.services.postings import _trim_body_html

    evaluator = get_evaluator()
    if evaluator is None:
        return
    snapshot = get_current_guideline_for_eval()
    if snapshot is None:
        return

    lock_conn = SessionLocal()
    if not _try_eval_advisory_lock(lock_conn):
        # 다른 프로세스가 이미 평가 백필 중 — 중복 실행 안 함
        lock_conn.close()
        logger.info("fill-missing: advisory lock busy — another worker is evaluating")
        return
    try:
        with SessionLocal() as db:
            rows = list(
                db.execute(
                    select(
                        GrantPosting.id,
                        GrantPosting.source_site,
                        GrantPosting.title,
                        GrantPosting.content_html,
                    ).where(_missing_eval_clause())
                ).all()
            )
        if not rows:
            _set_progress(running=False, total=0, processed=0, updated=0,
                          failed=0, finished_at=datetime.now(timezone.utc).isoformat())
            return
        logger.info("fill-missing: evaluating %d unevaluated UNREVIEWED postings", len(rows))
        _set_progress(
            running=True, total=len(rows), processed=0, updated=0, failed=0,
            started_at=datetime.now(timezone.utc).isoformat(), finished_at=None,
        )

        updated = 0
        failed = 0
        for pid, site, title, html in rows:
            trimmed = _trim_body_html(site, html or "")
            body = _strip_tags_for_match(trimmed or "")
            result = evaluator.evaluate(
                guideline_md=snapshot.content_md,
                posting_title=title or "",
                posting_body=body,
                allow_short=True,  # 본문 부실해도 제목으로 추측 평가
            )
            with SessionLocal() as db:
                if result is None:
                    db.execute(
                        update(GrantPosting)
                        .where(GrantPosting.id == pid)
                        .values(
                            relevance_score=None,
                            relevance_reason=None,
                            evaluated_with_guideline_version=snapshot.version,
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
                            evaluated_with_guideline_version=snapshot.version,
                            evaluation_failed=False,
                        )
                    )
                    updated += 1
                db.commit()
            # 매 건 처리 후 진행 상태 갱신 (프론트 프로그레스바가 폴링)
            _set_progress(processed=updated + failed, updated=updated, failed=failed)
        logger.info("fill-missing done — updated=%d failed=%d / total=%d",
                    updated, failed, len(rows))
    finally:
        _set_progress(running=False, finished_at=datetime.now(timezone.utc).isoformat())
        lock_conn.close()  # session-level advisory lock 자동 해제


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
