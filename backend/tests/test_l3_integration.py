"""L3 · 모듈 통합 — 스크래퍼 hook을 가짜 페이지로 주입하여
sanitize + parse_period + screen + upsert 풀 사이클을 검증.

라이브 사이트는 호출하지 않는다. BizinfoScraper의 iter_listing_pages /
fetch_detail을 monkeypatch로 교체해 100% 결정적 검증.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from total_support.db import (
    GrantCollectionRun,
    GrantPosting,
    GrantSystemLog,
    SessionLocal,
)
from total_support.scrapers.base import ListingItem
from total_support.scrapers.bizinfo import BizinfoScraper, _extract_period

# ============================================================
# fixture: 가짜 BizinfoScraper — 네트워크 호출 없음
# ============================================================
class FakeBizinfo(BizinfoScraper):
    """1페이지 3건만 yield하고, fetch_detail은 사전 정의 HTML 반환."""

    PAGE_ITEMS = [
        ListingItem(
            source_id="PBLN_L3_TEST_001",
            title="L3 통합 테스트 · AI 헬스케어 진단 모델 R&D 지원",
            detail_url="https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_L3_TEST_001",
            posting_status_hint="ONGOING",
        ),
        ListingItem(
            source_id="PBLN_L3_TEST_002",
            title="L3 통합 테스트 · 일반 수출 바우처 (매칭 없음)",
            detail_url="https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_L3_TEST_002",
            posting_status_hint="ONGOING",
        ),
        ListingItem(
            source_id="PBLN_L3_TEST_003",
            title="L3 통합 · 상시모집 웰니스 컨설팅 바우처 (예산 소진 시)",
            detail_url="https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_L3_TEST_003",
            posting_status_hint="ONGOING",
        ),
    ]

    DETAIL_HTML = {
        "PBLN_L3_TEST_001": (
            """<table><tr><th>신청기간</th><td>2026-06-01 ~ 2026-06-30</td></tr></table>"""
            """<p>본 사업은 <b>인공지능 진단 모델</b>을 활용한 의료기기 SaaS R&D 지원입니다.</p>"""
            """<script>alert('xss')</script>"""
        ),
        "PBLN_L3_TEST_002": (
            """<table><tr><th>신청기간</th><td>2026-05-01 ~ 2026-12-31</td></tr></table>"""
            """<p>일반 수출 바우처 — 분야 무관 지원사업.</p>"""
        ),
        "PBLN_L3_TEST_003": (
            """<table><tr><th>신청기간</th><td>상시모집 (예산 소진 시 마감)</td></tr></table>"""
            """<p>웰니스 분야 시제품 컨설팅 바우처입니다.</p>"""
        ),
    }

    def __init__(self):
        # 네트워크 client 없이도 동작하도록 부모 __init__ 우회 — 필수 멤버만 세팅
        # 부모는 httpx Client 생성하므로 그대로 호출하되 close 가능 상태로 둔다.
        super().__init__()
        self.MAX_PAGES = 1

    def iter_listing_pages(self):
        yield list(self.PAGE_ITEMS)

    def fetch_detail(self, item):
        html = self.DETAIL_HTML[item.source_id]
        return html, _extract_period(html)


# ============================================================
# helper: 테스트 데이터 사전/사후 정리
# ============================================================
TEST_IDS = ("PBLN_L3_TEST_001", "PBLN_L3_TEST_002", "PBLN_L3_TEST_003")


def _cleanup():
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM tb_grant_postings WHERE source_id = ANY(:ids)"
            ).bindparams(ids=list(TEST_IDS))
        )
        db.execute(
            text("DELETE FROM tb_grant_system_logs WHERE message LIKE '%L3_TEST%'")
        )
        db.commit()


@pytest.fixture(autouse=True)
def cleanup_before_after():
    _cleanup()
    yield
    _cleanup()


# ============================================================
# 테스트
# ============================================================
def test_l3_full_pipeline_3_postings_one_run_row():
    """수집 1회 → 3건 INSERT + 1 run row OK + system_logs 1+."""
    scraper = FakeBizinfo()
    try:
        result = scraper.run(trigger_kind="MANUAL", triggered_by="l3_test")
    finally:
        scraper.close()

    assert result.new_records == 3
    assert result.updated_records == 0
    assert result.pages_visited == 1

    with SessionLocal() as db:
        rows = list(
            db.execute(
                select(GrantPosting).where(GrantPosting.source_id.in_(TEST_IDS))
            ).scalars()
        )
        assert len(rows) == 3

        by_id = {p.source_id: p for p in rows}

        # === Posting 1: AI + 헬스케어 매칭, P1 파싱 ===
        p1 = by_id["PBLN_L3_TEST_001"]
        assert p1.ai_suitability == "HIGH"
        # assigned_fields는 콤마 문자열로 저장
        assert "AI" in (p1.assigned_fields or "")
        assert "헬스케어" in (p1.assigned_fields or "") or "헬스케어" in (p1.assigned_fields or "")
        assert str(p1.start_date) == "2026-06-01"
        assert str(p1.end_date) == "2026-06-30"
        # sanitize: <script> 제거 확인
        assert "<script" not in (p1.content_html or "")
        assert "alert" not in (p1.content_html or "")

        # === Posting 2: 매칭 없음 → NORMAL ===
        p2 = by_id["PBLN_L3_TEST_002"]
        assert p2.ai_suitability == "NORMAL"
        assert p2.assigned_fields in (None, "")

        # === Posting 3: 웰니스 매칭, P4 상시 → start/end None ===
        p3 = by_id["PBLN_L3_TEST_003"]
        assert p3.ai_suitability == "HIGH"
        assert "웰니스" in (p3.assigned_fields or "")
        assert p3.start_date is None
        assert p3.end_date is None
        assert "상시" in (p3.raw_period or "")

        # === run row 1건 OK ===
        last_run = db.execute(
            select(GrantCollectionRun)
            .where(
                GrantCollectionRun.source_site == "BIZINFO",
                GrantCollectionRun.triggered_by == "l3_test",
            )
            .order_by(GrantCollectionRun.id.desc())
            .limit(1)
        ).scalar()
        assert last_run is not None
        assert last_run.status == "OK"
        assert last_run.new_records == 3
        assert last_run.trigger_kind == "MANUAL"

        # === system_logs INFO 1+ ===
        log_count = db.execute(
            select(GrantSystemLog).where(
                GrantSystemLog.source_site == "BIZINFO",
                GrantSystemLog.message.like("%MANUAL 수집 OK%"),
            )
        ).scalars().all()
        assert len(log_count) >= 1


def test_l3_all_expired_2pages_early_break():
    """ALL_EXPIRED_2PAGES: 페이지 내 모든 항목 end_date 만료가 2회 연속 → break."""
    import re
    from total_support.scrapers.base import ListingItem
    from total_support.scrapers.bizinfo import BizinfoScraper, _extract_period

    # 만료된 날짜만 가진 fixture (오늘 2026-05-22 기준 2024년 마감)
    EXPIRED_HTML = """<table><tr><th>신청기간</th><td>2024-01-01 ~ 2024-02-28</td></tr></table>"""

    class ExpiredScraper(BizinfoScraper):
        SITE_CODE = "BIZINFO"

        def __init__(self):
            super().__init__()
            self.MAX_PAGES = 10
            self._page_num = 0

        def iter_listing_pages(self):
            # 페이지 1: 만료만 — 카운터 1
            # 페이지 2: 만료만 — 카운터 2 → break (ALL_EXPIRED_2PAGES)
            for p in range(1, 5):
                items = [
                    ListingItem(
                        source_id=f"PBLN_EXP_TEST_P{p}_N{n}",
                        title=f"L3 expired test p{p} n{n}",
                        detail_url=f"https://x?pblancId=PBLN_EXP_TEST_P{p}_N{n}",
                        posting_status_hint="ONGOING",
                    )
                    for n in range(2)
                ]
                yield items

        def fetch_detail(self, item):
            return EXPIRED_HTML, _extract_period(EXPIRED_HTML)

    # cleanup
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM tb_grant_postings WHERE source_id LIKE 'PBLN_EXP_TEST_%'")
        )
        db.commit()

    s = ExpiredScraper()
    try:
        result = s.run(trigger_kind="MANUAL", triggered_by="l3_expired_test")
    finally:
        s.close()

    # cleanup after
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM tb_grant_postings WHERE source_id LIKE 'PBLN_EXP_TEST_%'")
        )
        db.commit()

    # 페이지 1, 2 모두 처리 → 2번째에서 break
    assert result.pages_visited == 2
    assert result.early_break_reason == "ALL_EXPIRED_2PAGES"
    assert result.new_records == 4  # 2건 × 2페이지


def test_l3_early_break_on_zero_new_page():
    """이미 적재된 ID만 있는 페이지 → Early Break."""
    # 1차 수집 — 모두 신규
    s1 = FakeBizinfo()
    try:
        s1.run(trigger_kind="MANUAL", triggered_by="l3_first")
    finally:
        s1.close()

    # 2차 수집 — 동일 페이지 → 모두 기존, 신규 0건 → Early Break ZERO_NEW_PAGE
    s2 = FakeBizinfo()
    try:
        r2 = s2.run(trigger_kind="MANUAL", triggered_by="l3_second")
    finally:
        s2.close()

    assert r2.new_records == 0
    assert r2.early_break_reason == "ZERO_NEW_PAGE"
    assert r2.pages_visited == 1
