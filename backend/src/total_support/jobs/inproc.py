"""In-process 비동기 실행기 — Redis/Celery 없는 환경의 fallback.

설계:
- daemon thread 1개로 단일 스크래퍼 실행
- 같은 사이트의 잡이 RUNNING이면 신규 거부 (HTTP 409)
- 시작 즉시 job_id 반환 → HTTP 호출이 hang 안 함
- 결과/실패는 tb_grant_collection_runs와 tb_grant_system_logs에 적재

운영용은 Celery + Redis가 우선. dev/단일팀 환경에선 이 fallback이 충분.
"""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

# ============================================================
# 사이트별 RUNNING 상태 추적 (동시 실행 방지)
# ============================================================
_LOCK = threading.Lock()
_RUNNING: dict[str, "JobHandle"] = {}  # site → handle


@dataclass(slots=True)
class JobHandle:
    job_id: str
    site: str
    started_at: datetime
    thread: threading.Thread


def is_running(site: str) -> JobHandle | None:
    """해당 사이트의 RUNNING 잡 핸들 또는 None."""
    with _LOCK:
        h = _RUNNING.get(site)
        if h is not None and not h.thread.is_alive():
            # 이미 끝난 잡이면 레지스트리에서 제거
            _RUNNING.pop(site, None)
            return None
        return h


def trigger(
    site: str,
    *,
    trigger_kind: str = "MANUAL",
    triggered_by: str = "api",
) -> str:
    """daemon thread로 스크래퍼 실행. 즉시 job_id 반환.

    Raises:
        RuntimeError: 같은 사이트가 이미 RUNNING.
    """
    if site not in ("BIZINFO", "IRIS", "SBA"):
        raise ValueError(f"알 수 없는 site: {site}")

    with _LOCK:
        existing = _RUNNING.get(site)
        if existing is not None and existing.thread.is_alive():
            raise RuntimeError(
                f"{site} 잡이 이미 in-process 실행 중 (job {existing.job_id})"
            )

    job_id = uuid.uuid4().hex[:12]

    def _worker() -> None:
        # 지연 임포트 — 모듈 로드 사이클 회피
        from total_support.db import SessionLocal
        from total_support.observability.logger import LogCategory, LogLevel, log_event
        from total_support.scrapers.bizinfo import BizinfoScraper
        from total_support.scrapers.iris import IrisScraper
        from total_support.scrapers.sba import SbaScraper

        scraper_cls: dict[str, Any] = {
            "BIZINFO": BizinfoScraper,
            "IRIS": IrisScraper,
            "SBA": SbaScraper,
        }[site]

        try:
            scraper = scraper_cls()
        except Exception as e:  # noqa: BLE001
            # 스크래퍼 생성 실패 (예: SBA Playwright 브라우저 미설치)
            with SessionLocal() as db:
                log_event(
                    db,
                    LogLevel.ERROR,
                    LogCategory.SCRAPER,
                    f"{site} 스크래퍼 초기화 실패: {type(e).__name__}: {e}",
                    source_site=site,
                    payload={"job_id": job_id, "trace": traceback.format_exc(limit=3)},
                )
                db.commit()
            return
        try:
            scraper.run(trigger_kind=trigger_kind, triggered_by=triggered_by)
        except Exception as e:  # noqa: BLE001
            # run() 내부에서 잡힌 예외는 collection_runs에 FAIL로 적재됨.
            # 여기까지 오는 건 매우 예외적 (run 자체가 깨짐) — 로그만 남김.
            with SessionLocal() as db:
                log_event(
                    db,
                    LogLevel.ERROR,
                    LogCategory.SCRAPER,
                    f"{site} 잡 비정상 종료: {type(e).__name__}: {e}",
                    source_site=site,
                    payload={"job_id": job_id, "trace": traceback.format_exc(limit=3)},
                )
                db.commit()
        finally:
            try:
                scraper.close()
            except Exception:  # noqa: BLE001
                pass
            # 레지스트리 정리
            with _LOCK:
                _RUNNING.pop(site, None)

    t = threading.Thread(target=_worker, daemon=True, name=f"scrape-{site}-{job_id}")
    handle = JobHandle(job_id=job_id, site=site, started_at=datetime.now(timezone.utc), thread=t)
    with _LOCK:
        _RUNNING[site] = handle
    t.start()
    return job_id
