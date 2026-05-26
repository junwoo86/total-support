"""스크래퍼 공통 베이스 — PRD §2.2 (Early Break) + §2.4 (run 적재) + §7 (시퀀스).

표준 파이프라인:
1. RUNNING run 행을 INSERT (즉시 commit → 헬스 패널 폴링이 즉시 보게)
2. 페이지 순회 (사이트별 list_page() 구현)
3. 각 페이지에서 (source_id, title, detail_url) 추출
4. 이미 DB에 있는 source_id는 상세 fetch 스킵
5. 페이지 전체에서 신규 0건이면 **Early Break** (PRD §2.2)
6. 신규 ID에 대해 fetch_detail() → sanitize_html → parse_period → screen → upsert
7. RUN 완료 후 status=OK/WARN/FAIL로 UPDATE
8. 예외 발생 시 status=FAIL + error_message 기록

사이트별 구현이 채워야 할 것:
- SITE_CODE: BIZINFO/IRIS/SBA
- iter_listing_pages(): yield list[ListingItem]
- fetch_detail(item): (content_html_raw, raw_period_text)
"""

from __future__ import annotations

import time
import traceback
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from total_support.db import (
    GrantCollectionRun,
    GrantDomain,
    GrantKeyword,
    GrantPosting,
    KEYWORD_VERSION_SEQ_NAME,
    SessionLocal,
    seoul_today_expr,
)
from total_support.observability.logger import LogCategory, LogLevel, log_event
from total_support.parsers import parse_period, sanitize_html
from total_support.screening import KeywordSpec, screen


# ============================================================
# 입력/출력 DTO
# ============================================================
@dataclass(slots=True)
class ListingItem:
    """목록 페이지에서 추출한 1행 — 상세 진입 전 정보."""

    source_id: str
    title: str
    detail_url: str
    #: 사이트별로 목록에서 함께 노출되는 메타 (옵션)
    posting_status_hint: str | None = None  # ONGOING / SCHEDULED 단서
    raw_period_hint: str | None = None      # 목록에 접수기간 노출되면


@dataclass(slots=True)
class ScrapeResult:
    """run 1회 종료 시 통계."""

    new_records: int = 0
    updated_records: int = 0
    pages_visited: int = 0
    early_break_reason: str | None = None
    warnings: list[str] = field(default_factory=list)


# ============================================================
# 베이스 클래스
# ============================================================
class BaseScraper(ABC):
    """모든 사이트 스크래퍼의 공통 기반.

    하위 클래스는 SITE_CODE와 iter_listing_pages(), fetch_detail()을 구현한다.
    """

    SITE_CODE: str = ""              # "BIZINFO" / "IRIS" / "SBA"
    # 초기 수집은 페이지 수가 매우 많을 수 있으므로 충분히 크게.
    # 평소엔 Early Break(신규 0건 / 만료 페이지 연속 2회)이 먼저 멈춤.
    MAX_PAGES: int = 50
    URL_MAX_LEN: int = 950           # PRD §4.2: 950자 trim
    # 신규 중단 조건: 페이지 내 모든 항목이 end_date 만료(< 한국 오늘)인
    # 페이지가 N회 연속이면 멈춘다 (최신순 목록의 후반부는 모두 마감일 것).
    EXPIRED_STREAK_LIMIT: int = 2
    # 사이트별 본문 컨테이너 selector 후보 (스크리닝 노이즈 축소용 — A 제안).
    # 첫 번째부터 시도하고 모두 실패하면 fallback to 전체 HTML + WARN.
    # 빈 튜플이면 selector 적용 안 함 (= 기존 동작).
    BODY_SELECTORS: tuple[str, ...] = ()
    # 본문 영역이 의미를 가진다고 인정하는 최소 텍스트 길이.
    BODY_MIN_TEXT_LEN: int = 50

    # --------------------------------------------------------
    # 본문 selector 추출 (A 제안 — 스크리닝 노이즈 축소)
    # --------------------------------------------------------
    def extract_body_html(self, raw_html: str, *, source_id: str = "") -> str:
        """`BODY_SELECTORS` 첫 매치를 outerHTML 로 반환. 모두 실패 → 전체 HTML.

        실패 시 `self._body_selector_misses` 에 source_id 누적 → run 종료
        시점에 system_logs WARN 기록 + run status=WARN 으로 전환.
        스크래퍼가 사이트 마크업 변경을 모니터링하는 신호로 사용된다.
        """
        if not self.BODY_SELECTORS:
            return raw_html
        try:
            from selectolax.parser import HTMLParser
            tree = HTMLParser(raw_html)
        except Exception:  # noqa: BLE001
            return raw_html
        for sel in self.BODY_SELECTORS:
            node = tree.css_first(sel)
            if node is None:
                continue
            txt = (node.text(deep=True, strip=True) or "")
            if len(txt) < self.BODY_MIN_TEXT_LEN:
                continue
            html = node.html or ""
            if html:
                return html
        # 모든 selector 실패 — fallback + 누적
        self._body_selector_misses.append(source_id or "?")
        return raw_html

    # --------------------------------------------------------
    # 진입점
    # --------------------------------------------------------
    def run(self, *, trigger_kind: str = "MANUAL", triggered_by: str = "system") -> ScrapeResult:
        """동기 실행. 새 세션을 만들어 자체 트랜잭션으로 관리한다.

        Returns:
            ScrapeResult — 호출자에게 통계 반환.
        """
        assert self.SITE_CODE in ("BIZINFO", "IRIS", "SBA"), "SITE_CODE 미설정"
        started_at = datetime.now(timezone.utc)
        t0 = time.monotonic()

        # 1) RUNNING row 즉시 적재 (헬스 패널이 보게)
        with SessionLocal() as db:
            run_row = GrantCollectionRun(
                source_site=self.SITE_CODE,
                started_at=started_at,
                status="RUNNING",
                trigger_kind=trigger_kind,
                triggered_by=triggered_by,
            )
            db.add(run_row)
            db.commit()
            run_id = run_row.id

        result = ScrapeResult()
        status = "OK"
        err_msg: str | None = None
        self._body_selector_misses: list[str] = []

        try:
            # 2) 키워드 한 번만 로드 (페이지 순회 중 재사용)
            with SessionLocal() as db:
                kw_specs = _load_keyword_specs(db)
                kw_version = _get_keyword_version(db)

            # 3) 페이지 순회 + Early Break
            expired_streak = 0
            for page_items in self.iter_listing_pages():
                result.pages_visited += 1
                new_in_page, expired_only = self._process_page(
                    page_items, kw_specs, kw_version, result
                )

                # 진행도 즉시 DB 반영 (헬스 패널 폴링이 incremental하게 보게)
                self._update_run_progress(run_id, result)

                # 우선순위 1: ZERO_NEW_PAGE (모든 ID가 기존이면 더 볼 필요 없음)
                if new_in_page == 0:
                    result.early_break_reason = "ZERO_NEW_PAGE"
                    break

                # 우선순위 2: 페이지 내 모든 항목 만료 → N회 연속 시 중단.
                # PRD: 목록은 최신순이므로 후반부는 거의 다 마감.
                # 만료된 신규 공고를 수십 페이지에 걸쳐 끝없이 적재할 필요 없음.
                if expired_only:
                    expired_streak += 1
                    if expired_streak >= self.EXPIRED_STREAK_LIMIT:
                        result.early_break_reason = "ALL_EXPIRED_2PAGES"
                        break
                else:
                    expired_streak = 0

                if result.pages_visited >= self.MAX_PAGES:
                    result.early_break_reason = "END_OF_LIST"
                    break

            # 본문 selector 누락이 누적되면 사이트 마크업 변경 의심 → WARN.
            # 임계치: 신규의 30% 또는 5건 (둘 중 큰 값) 이상 fallback 발생.
            miss_count = len(self._body_selector_misses)
            miss_threshold = max(5, int((result.new_records or 0) * 0.3))
            if miss_count >= miss_threshold and self.BODY_SELECTORS:
                result.warnings.append(
                    f"BODY_SELECTOR_MISS x{miss_count} "
                    f"(selectors={list(self.BODY_SELECTORS)}, "
                    f"sample_ids={self._body_selector_misses[:5]}) "
                    f"— 사이트 마크업 변경 점검 필요"
                )

            if result.warnings:
                status = "WARN"
        except Exception as e:  # noqa: BLE001
            status = "FAIL"
            err_msg = f"{type(e).__name__}: {e}\n" + traceback.format_exc(limit=4)
            result.early_break_reason = "ERROR"

        # 4) 최종 통계 + 시스템 로그
        duration_ms = int((time.monotonic() - t0) * 1000)
        with SessionLocal() as db:
            row = db.get(GrantCollectionRun, run_id)
            if row is not None:
                row.status = status
                row.finished_at = datetime.now(timezone.utc)
                row.pages_visited = result.pages_visited
                row.new_records = result.new_records
                row.updated_records = result.updated_records
                row.early_break_reason = result.early_break_reason
                row.error_message = err_msg or (
                    "\n".join(result.warnings) if result.warnings else None
                )
                row.duration_ms = duration_ms

            # system_logs INFO/WARN/ERROR 1행
            log_event(
                db,
                LogLevel.INFO if status == "OK" else LogLevel.WARN if status == "WARN" else LogLevel.ERROR,
                LogCategory.SCRAPER,
                message=(
                    f"{self.SITE_CODE} {trigger_kind} 수집 {status} — "
                    f"신규 {result.new_records}건, 갱신 {result.updated_records}건, "
                    f"{result.pages_visited}페이지, {duration_ms}ms"
                ),
                source_site=self.SITE_CODE,
                payload={
                    "run_id": run_id,
                    "trigger_kind": trigger_kind,
                    "triggered_by": triggered_by,
                    "early_break": result.early_break_reason,
                    "warnings": result.warnings[:5],
                },
            )
            db.commit()
        return result

    # --------------------------------------------------------
    # 사이트별 hook (하위 클래스 구현)
    # --------------------------------------------------------
    @abstractmethod
    def iter_listing_pages(self) -> Iterator[list[ListingItem]]:
        """목록을 페이지 단위로 yield. 빈 페이지가 나오면 자체적으로 stop."""

    @abstractmethod
    def fetch_detail(self, item: ListingItem) -> tuple[str, str | None]:
        """상세 페이지를 가져와 (content_html_raw, raw_period_text)를 반환.

        sanitize는 base에서 일괄 처리하므로 raw HTML 그대로 반환.
        raw_period는 사이트별로 본문에서 추출(없으면 None).
        """

    def derive_posting_status(self, item: ListingItem) -> str:
        """상태 결정 (SCHEDULED/ONGOING/CLOSED). 사이트별 override 가능."""
        return item.posting_status_hint or "ONGOING"

    # --------------------------------------------------------
    # 페이지 처리 — Early Break 1단계
    # --------------------------------------------------------
    def _process_page(
        self,
        items: list[ListingItem],
        kw_specs: list[KeywordSpec],
        kw_version: int,
        result: ScrapeResult,
    ) -> tuple[int, bool]:
        """페이지 1개를 처리.

        Returns:
            (new_count, expired_only) — expired_only는 페이지 내 모든 항목이
            end_date 만료(< 한국 오늘)인지. None end_date(상시)는 만료 아님.
        """
        if not items:
            return 0, False

        new_count = 0
        with SessionLocal() as db:
            # 이미 존재하는 source_id 집합 조회 (Early Break 1단계 — 상세 스킵)
            existing_ids = set(
                db.execute(
                    select(GrantPosting.source_id).where(
                        GrantPosting.source_site == self.SITE_CODE,
                        GrantPosting.source_id.in_([i.source_id for i in items]),
                    )
                ).scalars().all()
            )

            for item in items:
                if item.source_id in existing_ids:
                    continue  # 상세 fetch 스킵 (PRD §2.2)
                try:
                    self._ingest_one(db, item, kw_specs, kw_version)
                    new_count += 1
                    result.new_records += 1
                except Exception as e:  # noqa: BLE001
                    result.warnings.append(
                        f"{item.source_id}: {type(e).__name__}: {e}"
                    )
                    log_event(
                        db,
                        LogLevel.WARN,
                        LogCategory.SCRAPER,
                        f"상세 파싱 실패 — {self.SITE_CODE}/{item.source_id}: {e}",
                        source_site=self.SITE_CODE,
                        payload={"title": item.title[:120], "error": str(e)},
                    )

            db.commit()

            # 페이지 내 모든 항목 만료 여부 — 처리 후 DB 기준으로 정확히 판정
            page_ids = [i.source_id for i in items]
            row = db.execute(
                select(
                    func.count(GrantPosting.id).label("total"),
                    func.count(GrantPosting.id)
                    .filter(
                        GrantPosting.end_date.is_not(None),
                        GrantPosting.end_date < seoul_today_expr(),
                    )
                    .label("expired"),
                ).where(
                    GrantPosting.source_site == self.SITE_CODE,
                    GrantPosting.source_id.in_(page_ids),
                )
            ).one()
            expired_only = (row.total > 0 and row.total == row.expired)
        return new_count, expired_only

    def _update_run_progress(self, run_id: int, result: ScrapeResult) -> None:
        """RUNNING run row의 진행 통계를 즉시 업데이트.

        헬스 패널이 30초 폴링으로 가져온 latest_run에서 페이지/신규 누적을
        실시간으로 보여주기 위함.
        """
        try:
            with SessionLocal() as db:
                row = db.get(GrantCollectionRun, run_id)
                if row is None:
                    return
                row.pages_visited = result.pages_visited
                row.new_records = result.new_records
                row.updated_records = result.updated_records
                db.commit()
        except Exception:  # noqa: BLE001
            # 진행도 갱신 실패가 본 작업을 중단시키면 안 된다.
            pass

    # --------------------------------------------------------
    # 단건 적재 (fetch → sanitize → parse → screen → upsert)
    # --------------------------------------------------------
    def _ingest_one(
        self,
        db: Session,
        item: ListingItem,
        kw_specs: list[KeywordSpec],
        kw_version: int,
    ) -> None:
        # 1) 상세 fetch
        raw_html, raw_period_text = self.fetch_detail(item)

        # 2) sanitize
        content_html = sanitize_html(raw_html)
        plain_body = _strip_tags_for_match(content_html)

        # 3) 접수기간 파싱 (목록 hint 우선, 없으면 상세 텍스트)
        raw_period = (item.raw_period_hint or raw_period_text or "").strip()
        if raw_period:
            outcome = parse_period(raw_period)
            if outcome.rule == "P6":
                log_event(
                    db,
                    LogLevel.WARN,
                    LogCategory.PARSE_PERIOD,
                    f"PARSE_UNKNOWN — {self.SITE_CODE}/{item.source_id}",
                    source_site=self.SITE_CODE,
                    payload={"raw": raw_period[:200]},
                )
            start_date = outcome.start_date
            end_date = outcome.end_date
        else:
            raw_period = "(접수기간 표기 없음)"
            start_date = None
            end_date = None

        # 4) 스크리닝 — 본문 selector 적용된 plain text 사용
        screen_text = item.title + "\n" + plain_body
        screen_result = screen(screen_text, kw_specs)

        # 4-1) 회사 적합도 평가 (Gemini · 지침이 있을 때만)
        rel_score, rel_reason, rel_version, rel_failed = _try_evaluate_relevance(
            title=item.title, body_plain=plain_body,
        )

        # 5) URL trim + 경고 로깅
        detail_url = item.detail_url
        if len(detail_url) > self.URL_MAX_LEN:
            log_event(
                db,
                LogLevel.WARN,
                LogCategory.URL_TRUNCATED,
                f"detail_url 950자 초과 trim — {self.SITE_CODE}/{item.source_id}",
                source_site=self.SITE_CODE,
                payload={"original_len": len(detail_url), "trimmed_len": self.URL_MAX_LEN},
            )
            detail_url = detail_url[: self.URL_MAX_LEN]

        # 6) upsert (PRD §4.2 unique idx: source_site + source_id)
        stmt = pg_insert(GrantPosting).values(
            source_site=self.SITE_CODE,
            source_id=item.source_id,
            title=item.title[:500],
            detail_url=detail_url,
            content_html=content_html,
            raw_period=raw_period,
            start_date=start_date,
            end_date=end_date,
            posting_status=self.derive_posting_status(item),
            assigned_fields=screen_result.assigned_fields,
            ai_suitability=screen_result.ai_suitability,
            screened_with_version=kw_version,
            relevance_score=rel_score,
            relevance_reason=rel_reason,
            evaluated_with_guideline_version=rel_version,
            evaluation_failed=rel_failed,
            first_seen_at=func.now(),
            last_updated_at=func.now(),
        )
        # 평가 점수는 새로 산출되었거나 실패 플래그가 잡힌 경우에만 덮어쓰기
        # (None+failed=false 로 기존 값 지우지 않음).
        rel_overrides: dict = {}
        if rel_score is not None or rel_failed:
            rel_overrides = {
                "relevance_score": stmt.excluded.relevance_score,
                "relevance_reason": stmt.excluded.relevance_reason,
                "evaluated_with_guideline_version": stmt.excluded.evaluated_with_guideline_version,
                "evaluation_failed": stmt.excluded.evaluation_failed,
            }
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_site", "source_id"],
            set_={
                "title": stmt.excluded.title,
                "detail_url": stmt.excluded.detail_url,
                "content_html": stmt.excluded.content_html,
                "raw_period": stmt.excluded.raw_period,
                "start_date": stmt.excluded.start_date,
                "end_date": stmt.excluded.end_date,
                "posting_status": stmt.excluded.posting_status,
                "assigned_fields": stmt.excluded.assigned_fields,
                "ai_suitability": stmt.excluded.ai_suitability,
                "screened_with_version": stmt.excluded.screened_with_version,
                "last_updated_at": func.now(),
                **rel_overrides,
            },
        )
        db.execute(stmt)


# ============================================================
# 유틸
# ============================================================
def _load_keyword_specs(db: Session) -> list[KeywordSpec]:
    """enabled=TRUE 키워드만 ScreenSpec으로 변환."""
    rows = db.execute(
        select(GrantKeyword, GrantDomain)
        .join(GrantDomain, GrantDomain.id == GrantKeyword.domain_id)
        .where(GrantKeyword.enabled.is_(True), GrantDomain.enabled.is_(True))
    ).all()
    return [
        KeywordSpec(
            keyword=k.keyword,
            match_mode=k.match_mode,
            domain_label=d.label_ko,
            case_sensitive=k.case_sensitive,
            negative_context=tuple(k.negative_context or ()),
            enabled=True,
        )
        for (k, d) in rows
    ]


def _get_keyword_version(db: Session) -> int:
    """현재 키워드 버전 — sequence의 last_value.

    PRD §3.3.3: pg_sequences.last_value를 읽는다. currval은 같은 세션에서
    nextval 호출이 선행되어야 하므로 부적합.
    """
    from sqlalchemy import text

    value = db.execute(
        text(f"SELECT last_value FROM {KEYWORD_VERSION_SEQ_NAME}")
    ).scalar()
    return int(value or 0)


def _strip_tags_for_match(html: str) -> str:
    """HTML에서 태그를 빼고 텍스트만 (간단). 매칭용이라 정밀도 적당."""
    if not html:
        return ""
    import re
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _try_evaluate_relevance(
    *, title: str, body_plain: str,
) -> tuple[int | None, str | None, int | None, bool]:
    """수집 시점 회사 적합도 평가 — Gemini + 회사 지침.

    Returns:
        (score 0~100, reason, guideline.version, failed_flag)
        - 지침 없음 / evaluator 비활성 / 본문 짧음 → (None, None, None, False)
          = "평가 안 함" — UI 에서 "—" 로 표시.
        - Gemini 3회 재시도 실패                → (None, None, version, True)
          = "분석 실패" — UI 에서 최상단 노출.
        - 정상 평가                              → (score, reason, version, False).

    스크래퍼 파이프라인이 LLM 장애로 중단되지 않도록 모든 예외 swallow.
    """
    if not body_plain or len(body_plain) < 30:
        return None, None, None, False
    try:
        from total_support.services.evaluator import get_evaluator
        from total_support.services.guidelines import get_current_guideline_for_eval

        guideline = get_current_guideline_for_eval()
        if not guideline:
            return None, None, None, False  # 회사 지침 미설정 → 평가 안 함
        evaluator = get_evaluator()
        if evaluator is None:
            return None, None, None, False  # ADC 미설정 → 평가 안 함
        result = evaluator.evaluate(
            guideline_md=guideline.content_md,
            posting_title=title,
            posting_body=body_plain,
        )
        if result is None:
            # 평가 시도했으나 3회 재시도 모두 실패 — failed=True 로 기록
            return None, None, guideline.version, True
        return result.score, result.reason, guideline.version, False
    except Exception:  # noqa: BLE001
        return None, None, None, False
