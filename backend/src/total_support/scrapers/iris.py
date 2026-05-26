"""IRIS (범부처 R&D) 스크래퍼 — PRD §2.1 B.

목록: https://www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do (Form POST)
hidden 필드: pageIndex, ancmPrg(=ancmPre/ancmIng), ancmTl, bsnsAncmTl, blngGovdSeArr 등.

PRD §2.1 핵심 제약 (★):
- 상세는 POST 전용. GET 직접 접근 시 빈 화면.
- → detail_url에는 **목록 URL을 저장**한다.
- → 본 모듈은 별도 POST로 상세 HTML을 가져와 content_html을 보존 (자체 상세 뷰용).
- → 프론트의 "원본 IRIS 열기" 버튼은 목록 URL로 안내 (이미 ui-kit.jsx 구현됨).

식별자 추출: a[onclick]에서
  f_bsnsAncmBtinSituListForm_view('012345','ancmIng')  → 6자리 ancmId.

수집 대상 탭: ancmIng + ancmPre (ancmEnd 제외).
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
BASE_URL: Final = "https://www.iris.go.kr"
LIST_PATH: Final = "/contents/retrieveBsnsAncmBtinSituListView.do"
DETAIL_PATH: Final = "/contents/retrieveBsnsAncmView.do"

# PRD §2.1 매트릭스 — 수집 대상 탭만
TARGET_TABS = (
    ("ancmIng", "ONGOING"),   # 접수중
    ("ancmPre", "SCHEDULED"), # 접수예정
)

# a[onclick]에서 (ancmId, ancmPrg) 추출
_ANCM_RE = re.compile(
    r"f_bsnsAncmBtinSituListForm_view\(\s*'(\d{6})'\s*,\s*'(ancm(?:Pre|Ing|End))'\s*\)"
)

# 페이지 카운트
_TOTAL_PAGE_SEL = "span#totalPage b, p.page_info span#totalPage b"

# 상세 본문에서 접수기간 추출 — 라벨 다음 셀
_DETAIL_PERIOD_RE = re.compile(
    r"접수기간\s*[:：]?\s*([\d.\-/~ ()월화수목금토일까지: ]+)"
)


class IrisScraper(BaseScraper):
    """IRIS Form POST 기반 스크래퍼 — 수집 제어 난이도 중상."""

    SITE_CODE = "IRIS"
    ROWS_PER_PAGE = 10  # IRIS 기본값
    # 실측 (2026-05-26): IRIS 의 POST 응답은 list view 와 같은 page shell 을
    # 반환하므로 #content 가 가장 의미있는 본문 영역. 실패 시 fallback.
    BODY_SELECTORS = ("#content", "#contentWrap")

    def __init__(self, *, timeout_s: float = 45.0) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout_s,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; TotalSupport/0.1; +contact@biocom.kr)"
                ),
                "Accept-Language": "ko-KR,ko;q=0.9",
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
        )
        #: 같은 ID가 여러 탭에 노출될 수 있으니 dedupe
        self._seen_ids: set[str] = set()
        #: 상태 hint를 ancmPrg 기반으로 결정하기 위해 fetch 단계에서 사용
        self._tab_status: dict[str, str] = {}

    # --------------------------------------------------------
    # base hook 1: 목록 페이지 순회 (탭별 + 페이지별)
    # --------------------------------------------------------
    def iter_listing_pages(self) -> Iterator[list[ListingItem]]:
        for ancmPrg, posting_status in TARGET_TABS:
            # 첫 페이지 fetch → totalPage 확인
            total_page = 1
            for page in range(1, self.MAX_PAGES + 1):
                html = self._post_list(ancmPrg=ancmPrg, page_index=page)
                items = self._parse_list(html, ancmPrg=ancmPrg, posting_status=posting_status)
                if page == 1:
                    total_page = _parse_total_page(html)
                if not items:
                    break
                yield items
                if page >= total_page:
                    break

    # --------------------------------------------------------
    # base hook 2: 상세 페이지 fetch (POST 전용 ★)
    # --------------------------------------------------------
    def fetch_detail(self, item: ListingItem) -> tuple[str, str | None]:
        ancmPrg = self._tab_status.get(item.source_id, "ancmIng")
        try:
            r = self._client.post(
                DETAIL_PATH,
                data={
                    "ancmId": item.source_id,
                    "ancmPrg": ancmPrg,
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"IRIS 상세 POST 실패: {e}") from e

        html = r.text
        period = _extract_detail_period(html)
        body_html = self.extract_body_html(html, source_id=item.source_id)
        return body_html, period

    def derive_posting_status(self, item: ListingItem) -> str:
        return item.posting_status_hint or "ONGOING"

    # --------------------------------------------------------
    # 정리
    # --------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "IrisScraper":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --------------------------------------------------------
    # 내부: 목록 POST
    # --------------------------------------------------------
    def _post_list(self, *, ancmPrg: str, page_index: int) -> str:
        """PRD §2.1 IRIS: hidden 필드를 채워 Form POST."""
        data = {
            "pageIndex": str(page_index),
            "ancmPrg": ancmPrg,
            # 검색 조건 hidden 필드 (실측 기반 기본값)
            "ancmTl": "",
            "bsnsAncmTl": "",
            "blngGovdSeArr": "",
            "rowsPerPage": str(self.ROWS_PER_PAGE),
        }
        try:
            r = self._client.post(LIST_PATH, data=data)
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(
                f"IRIS 목록 POST 실패 (tab={ancmPrg}, page={page_index}): {e}"
            ) from e
        return r.text

    # --------------------------------------------------------
    # 내부: 목록 HTML 파싱
    # --------------------------------------------------------
    def _parse_list(
        self, html: str, *, ancmPrg: str, posting_status: str
    ) -> list[ListingItem]:
        """행에서 ancmId + 제목 추출. PRD §2.1 매트릭스."""
        tree = HTMLParser(html)
        items: list[ListingItem] = []

        # 행 어디에 있든 onclick에 f_bsnsAncmBtinSituListForm_view를 가진 모든 노드
        candidates = []
        for n in tree.css("a"):
            on = n.attributes.get("onclick") or ""
            if "f_bsnsAncmBtinSituListForm_view" in on:
                candidates.append(n)
        # 일부 사이트는 tr/td/span에 onclick을 둘 수도 있어 폴백
        if not candidates:
            for n in tree.css("[onclick]"):
                on = n.attributes.get("onclick") or ""
                if "f_bsnsAncmBtinSituListForm_view" in on:
                    candidates.append(n)

        for a in candidates:
            on = a.attributes.get("onclick") or ""
            m = _ANCM_RE.search(on)
            if not m:
                continue
            ancm_id, tag = m.group(1), m.group(2)
            if tag == "ancmEnd":
                # PRD §2.1: ancmEnd는 수집 대상 제외
                continue
            if ancm_id in self._seen_ids:
                continue
            self._seen_ids.add(ancm_id)
            self._tab_status[ancm_id] = ancmPrg

            title = _clean(a.text(deep=True, strip=True))
            if not title:
                # 행에서 다음 텍스트 셀
                parent_tr = _closest(a, "tr")
                if parent_tr is not None:
                    title = _clean(parent_tr.text(deep=True, strip=True))[:300]
            if not title:
                continue

            # detail_url은 PRD §2.1 ★: 목록 페이지를 저장 (POST 전용 제약)
            detail_list_url = (
                f"{BASE_URL}{LIST_PATH}"
                f"?ancmPrg={ancmPrg}&ancmId={ancm_id}"
            )
            items.append(
                ListingItem(
                    source_id=ancm_id,
                    title=title,
                    detail_url=detail_list_url,
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


def _parse_total_page(html: str) -> int:
    """totalPage span에서 페이지 수 추출. 못 찾으면 1."""
    tree = HTMLParser(html)
    node = tree.css_first(_TOTAL_PAGE_SEL)
    if node is None:
        return 1
    try:
        return max(1, int(_clean(node.text(deep=True, strip=True))))
    except ValueError:
        return 1


def _extract_detail_period(html: str) -> str | None:
    """상세 본문에서 접수기간 텍스트 추출."""
    text = HTMLParser(html).text(separator=" ", strip=True)
    m = _DETAIL_PERIOD_RE.search(text)
    if not m:
        return None
    raw = _clean(m.group(1))
    return raw if len(raw) >= 5 else None
