"""SBA (서울경제진흥원) 스크래퍼 — PRD §2.1 C.

대상 URL (수집 대상 2개):
- OngoingList.aspx   (접수중)
- PlanedList.aspx    (접수예정)
- (ClosedList.aspx는 PRD §2.1에 따라 수집 제외)

핵심 난점:
- ASP.NET WebForms `__doPostBack(...)`. VIEWSTATE가 ~146,668 byte로 매우 큼.
- httpx로 페이로드 복제는 가능하지만 매우 취약 → **Playwright 헤드리스로 페이징 스크립트를 실제 구동**하는 게 안정적 (PRD §2.1 권장).
- ViewState 만료 시 새 세션 재발급 후 1회 추가 재시도 (§8.3).

식별자 추출: 본문 HTML 정규식
  mid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})
상세: /Pages/BusinessApply/PostingDetail.aspx?p=0&mid={guid} (GET 가능)
접수기간 라벨: "접수기간" 우측 칸 (실측: 2026-06-01 ~ 2026-06-27)
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Final

import httpx
from selectolax.parser import HTMLParser

from total_support.scrapers.base import BaseScraper, ListingItem

# ============================================================
# 사이트 상수
# ============================================================
BASE_URL: Final = "https://www.sba.seoul.kr"
DETAIL_PATH_FMT: Final = "/Pages/BusinessApply/PostingDetail.aspx?p=0&mid={mid}"

# (path, posting_status)
TARGET_LISTS = (
    ("/Pages/BusinessApply/OngoingList.aspx", "ONGOING"),
    ("/Pages/BusinessApply/PlanedList.aspx", "SCHEDULED"),
)

# GUID PK 추출 — PRD §2.1
_MID_RE = re.compile(
    r"mid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})",
    re.IGNORECASE,
)

# 페이징 스크립트 인자 추출
_PAGE_POSTBACK_RE = re.compile(
    r"__doPostBack\('(ctl00\$ctl00\$ContentPlaceHolder1\$MainContents\$"
    r"GridView1\$ctl13\$PagingRepeater\$ctl\d+\$PageNum)',''\)"
)

# 상세 본문에서 접수기간 추출
_DETAIL_PERIOD_RE = re.compile(
    r"접수기간\s*[:：]?\s*([\d.\-/~ ()월화수목금토일까지: ]+)"
)


class SbaScraper(BaseScraper):
    """SBA Playwright 기반 스크래퍼 — 수집 제어 난이도 중간.

    Playwright(Chromium headless)로 ASP.NET 페이지를 실제 구동해 VIEWSTATE
    관리 부담을 우회. 상세 페이지는 GET 가능하므로 httpx로 빠르게 fetch.
    """

    SITE_CODE = "SBA"
    DEFAULT_NAV_TIMEOUT_MS = 25_000

    def __init__(self, *, headless: bool = True) -> None:
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._context = self._browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        self._page = self._context.new_page()
        self._page.set_default_navigation_timeout(self.DEFAULT_NAV_TIMEOUT_MS)
        self._page.set_default_timeout(self.DEFAULT_NAV_TIMEOUT_MS)

        # 상세 fetch용 httpx 클라이언트 (GET 가능)
        self._http = httpx.Client(
            base_url=BASE_URL,
            timeout=30.0,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; TotalSupport/0.1)",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
        )
        self._seen_mids: set[str] = set()
        self._mid_status: dict[str, str] = {}

    # --------------------------------------------------------
    # base hook 1: 목록 페이지 순회 (URL별 + 페이징)
    # ASP.NET WebForms의 거대한 HTML(360KB+)에서 selectolax가 일부 a를
    # 놓치는 케이스가 있어, Playwright DOM에서 직접 추출하는 방식을 채택.
    # --------------------------------------------------------
    def iter_listing_pages(self) -> Iterator[list[ListingItem]]:
        for path, posting_status in TARGET_LISTS:
            self._page.goto(
                BASE_URL + path,
                wait_until="networkidle",
                timeout=self.DEFAULT_NAV_TIMEOUT_MS,
            )
            # GridView 렌더링 대기
            try:
                self._page.wait_for_selector("a[href*='mid=']", timeout=10000)
            except Exception:  # noqa: BLE001
                pass

            page_no = 1
            while page_no <= self.MAX_PAGES:
                items = self._extract_from_dom(posting_status)
                if not items:
                    # 진짜 빈 페이지면 다음 URL로 (raise 아님, 0건 정상 가능성)
                    break
                yield items
                page_no += 1
                if not self._goto_next_page():
                    break

    def _extract_from_dom(self, posting_status: str) -> list[ListingItem]:
        """GridView1의 메인 row(15-cell)만 정밀 추출.

        SBA 실측 구조 (id=ContentPlaceHolder1_MainContents_GridView1):
        - 메인 row: 15개 td. mid는 td[0..6, 10]의 onclick에 들어있음.
        - 사업명: row 내 `<a>` 태그의 textContent (placeholder 텍스트 미포함).
        - 접수기간: row 내 YYYY-MM-DD 두 개 (td[11]=start, td[12]=end).
        - 모바일 stacked row: cell_count==1 — 무시.
        - 헤더 row: TH만 — 무시.
        """
        rows = self._page.eval_on_selector_all(
            "table[id*='GridView1'] tr",
            r"""(trs) => trs.map(tr => {
                const cells = Array.from(tr.querySelectorAll('td'));
                if (cells.length < 10) return null;
                let mid = null;
                for (const c of cells) {
                    const oc = c.getAttribute('onclick') || '';
                    const m = oc.match(/mid=([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i);
                    if (m) { mid = m[1].toLowerCase(); break; }
                }
                if (!mid) return null;
                const aTexts = Array.from(tr.querySelectorAll('a'))
                    .map(a => (a.textContent || '').replace(/\s+/g, ' ').trim())
                    .filter(t => t.length >= 3);
                const fullText = (tr.textContent || '').replace(/\s+/g, ' ');
                const dates = fullText.match(/\d{4}-\d{2}-\d{2}/g) || [];
                return {
                    mid,
                    title: aTexts[0] || '',
                    start: dates[0] || '',
                    end: dates[1] || ''
                };
            }).filter(x => x !== null)"""
        )

        items = _rows_to_items(rows, posting_status, self._seen_mids)
        for it in items:
            self._mid_status[it.source_id] = posting_status
        return items

    def _goto_next_page(self) -> bool:
        """페이징 영역에서 '다음' 또는 다음 페이지 번호 링크를 클릭.

        Returns: 이동 성공 여부.
        """
        # 다음 페이지 링크 후보: PagingRepeater 내부 a[href*='__doPostBack']
        candidates = self._page.query_selector_all(
            "a[href*='PagingRepeater']"
        )
        if not candidates:
            return False
        # 가장 마지막 클릭 가능한 페이지 번호로 이동 (단순화)
        try:
            candidates[-1].click()
            self._page.wait_for_load_state("networkidle", timeout=self.DEFAULT_NAV_TIMEOUT_MS)
            return True
        except Exception:  # noqa: BLE001
            return False

    # --------------------------------------------------------
    # base hook 2: 상세 페이지 fetch (GET 가능)
    # --------------------------------------------------------
    def fetch_detail(self, item: ListingItem) -> tuple[str, str | None]:
        try:
            r = self._http.get(DETAIL_PATH_FMT.format(mid=item.source_id))
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"SBA 상세 GET 실패: {e}") from e

        html = r.text
        period = _extract_detail_period(html)
        return html, period

    def derive_posting_status(self, item: ListingItem) -> str:
        return item.posting_status_hint or "ONGOING"

    # --------------------------------------------------------
    # 정리
    # --------------------------------------------------------
    def close(self) -> None:
        try:
            self._http.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._context.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._browser.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            self._pw.stop()
        except Exception:  # noqa: BLE001
            pass

    def __enter__(self) -> "SbaScraper":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --------------------------------------------------------
    # 내부: 목록 HTML 파싱
    # --------------------------------------------------------
    def _parse_list(self, html: str, *, posting_status: str) -> list[ListingItem]:
        """본문에서 mid GUID를 찾고 같은 행의 텍스트를 title로 사용."""
        tree = HTMLParser(html)
        items: list[ListingItem] = []

        for a in tree.css("a[href]"):
            href = a.attributes.get("href") or ""
            m = _MID_RE.search(href)
            if not m:
                # onclick에 mid가 들어있는 경우도 있음
                on = a.attributes.get("onclick") or ""
                m = _MID_RE.search(on)
                if not m:
                    continue
            mid = m.group(1).lower()
            if mid in self._seen_mids:
                continue
            self._seen_mids.add(mid)
            self._mid_status[mid] = posting_status

            title = _clean(a.text(deep=True, strip=True))
            if not title:
                tr = _closest(a, "tr")
                if tr is not None:
                    title = _clean(tr.text(deep=True, strip=True))[:300]
            if not title:
                continue

            detail_url = BASE_URL + DETAIL_PATH_FMT.format(mid=mid)
            items.append(
                ListingItem(
                    source_id=mid,
                    title=title,
                    detail_url=detail_url,
                    posting_status_hint=posting_status,
                )
            )
        return items


# ============================================================
# 모듈 헬퍼
# ============================================================
def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _closest(node, tag: str):
    cur = node.parent
    while cur is not None:
        if cur.tag == tag:
            return cur
        cur = cur.parent
    return None


def _rows_to_items(
    rows: list[dict],
    posting_status: str,
    seen_mids: set[str],
) -> list[ListingItem]:
    """JS 추출 결과(dict 리스트)를 ListingItem 리스트로 변환.

    Playwright 의존성 없이 단위 테스트 가능하도록 분리. seen_mids 는
    호출자가 누적 관리(in-place 갱신).
    """
    items: list[ListingItem] = []
    for r in rows:
        mid = (r.get("mid") or "").lower()
        if not mid or mid in seen_mids:
            continue
        title = (r.get("title") or "").strip()
        if len(title) < 3:
            continue
        seen_mids.add(mid)
        start, end = (r.get("start") or "").strip(), (r.get("end") or "").strip()
        period_hint = f"{start} ~ {end}" if start and end else None
        items.append(
            ListingItem(
                source_id=mid,
                title=title[:480],
                detail_url=BASE_URL + DETAIL_PATH_FMT.format(mid=mid),
                posting_status_hint=posting_status,
                raw_period_hint=period_hint,
            )
        )
    return items


def _extract_detail_period(html: str) -> str | None:
    text = HTMLParser(html).text(separator=" ", strip=True)
    m = _DETAIL_PERIOD_RE.search(text)
    if not m:
        return None
    raw = _clean(m.group(1))
    return raw if len(raw) >= 5 else None
