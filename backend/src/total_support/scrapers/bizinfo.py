"""BIZINFO (기업마당) 스크래퍼 — PRD §2.1 A.

목록 엔드포인트: https://www.bizinfo.go.kr/sii/siia/selectSIIA200View.do?cpage={N}&rows=15
정적 HTML 응답이라 httpx + selectolax로 고속 파싱.

식별자: a[href]의 query string에서 pblancId=PBLN_\\d{12}
상세: /sii/siia/selectSIIA200Detail.do?pblancId={pblancId} (GET 직접 가능)
접수기간: 상세 본문 "신청기간" 라벨 다음 줄
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Final

import httpx
from selectolax.parser import HTMLParser, Node

from total_support.scrapers.base import BaseScraper, ListingItem

# ============================================================
# 사이트 상수
# ============================================================
BASE_URL: Final = "https://www.bizinfo.go.kr"
LIST_PATH: Final = "/sii/siia/selectSIIA200View.do"
DETAIL_PATH: Final = "/sii/siia/selectSIIA200Detail.do"

# href에서 pblancId 추출. PRD §2.1은 `PBLN_\d{12}`라 적혀있지만 실측 ID는
# 15자리(0 padding)이므로 6자 이상으로 관대하게 잡는다.
_PBLANC_RE = re.compile(r"pblancId=(PBLN_\d{6,})")

# 접수기간 라벨 다음 텍스트.
# G1 수정: 신청기간 라벨 이후 ~ 다음 두 번째 날짜까지 적극적으로 캡처.
# 'YYYY.MM.DD ~ YYYY.MM.DD' / 'YYYY-MM-DD ~ YYYY-MM-DD' / 'YYYY.MM.DD ~' (단편)
# 길이를 넉넉히 잡고 newline/탭은 잘라낸다.
_PERIOD_LABEL_RE = re.compile(
    r"(?:신청\s*기간|접수\s*기간|신청기간|접수기간)\s*[:：]?\s*"
    r"([0-9]{4}[.\-/][0-9]{1,2}[.\-/][0-9]{1,2}"     # 시작일 풀
    r"(?:\s*\([월화수목금토일]\))?"                      # 선택 요일
    r"(?:\s*~\s*"                                       # ~
    r"(?:[0-9]{4}[.\-/])?[0-9]{1,2}[.\-/][0-9]{1,2}"   # 종료일 (연도 생략 가능)
    r"(?:\s*\([월화수목금토일]\))?"
    r"(?:\s*[0-9]{1,2}:[0-9]{2})?"                     # 선택 시간
    r"(?:\s*까지)?"
    r")?)"
)


class BizinfoScraper(BaseScraper):
    """BIZINFO 정적 HTML 스크래퍼 — 수집 제어 난이도 낮음."""

    SITE_CODE = "BIZINFO"
    ROWS_PER_PAGE = 15
    # 실측 (2026-05-26): .view_cont 가 진짜 본문 (~400자), 페이지 전체는
    # ~18,000자로 노이즈 97%. fallback은 .sub_cont (헤더 포함).
    BODY_SELECTORS = (".view_cont", ".sub_cont")

    def __init__(self, *, timeout_s: float = 30.0, user_agent: str | None = None) -> None:
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout_s,
            headers={
                "User-Agent": user_agent
                or "Mozilla/5.0 (compatible; TotalSupport/0.1; +contact@biocom.kr)",
                "Accept-Language": "ko-KR,ko;q=0.9",
            },
            follow_redirects=True,
        )

    # --------------------------------------------------------
    # base hook 1: 목록 페이지 순회
    # --------------------------------------------------------
    def iter_listing_pages(self) -> Iterator[list[ListingItem]]:
        for page in range(1, self.MAX_PAGES + 1):
            try:
                r = self._client.get(
                    LIST_PATH,
                    params={"cpage": page, "rows": self.ROWS_PER_PAGE},
                )
                r.raise_for_status()
            except httpx.HTTPError as e:
                raise RuntimeError(f"BIZINFO 목록 조회 실패 (page={page}): {e}") from e

            items = self._parse_list(r.text)
            if not items:
                # 빈 페이지 → 더 이상 진행 안 함 (END_OF_LIST는 base가 자체적으로 판단)
                return
            yield items

    # --------------------------------------------------------
    # base hook 2: 상세 페이지 fetch
    # --------------------------------------------------------
    def fetch_detail(self, item: ListingItem) -> tuple[str, str | None]:
        try:
            r = self._client.get(DETAIL_PATH, params={"pblancId": item.source_id})
            r.raise_for_status()
        except httpx.HTTPError as e:
            raise RuntimeError(f"상세 조회 실패: {e}") from e

        html = r.text
        period_text = _extract_period(html)  # period 는 전체에서 찾는 게 안전
        body_html = self.extract_body_html(html, source_id=item.source_id)
        return body_html, period_text

    # --------------------------------------------------------
    # 정리
    # --------------------------------------------------------
    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "BizinfoScraper":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --------------------------------------------------------
    # 내부: 목록 HTML 파싱
    # --------------------------------------------------------
    def _parse_list(self, html: str) -> list[ListingItem]:
        tree = HTMLParser(html)
        seen: set[str] = set()
        items: list[ListingItem] = []

        # 행이 어디에 들어있든 pblancId 패턴을 가진 모든 a를 잡는다 (마크업 변경 내성).
        # selectolax의 부분 매칭 CSS 셀렉터(`[href*=...]`)는 백엔드에 따라 동작이
        # 불안정해, 전체 a를 가져와 직접 정규식으로 필터.
        for a in tree.css("a"):
            href = a.attributes.get("href") or ""
            m = _PBLANC_RE.search(href)
            if not m:
                continue
            sid = m.group(1)

            # 같은 ID가 여러 a로 노출되면 가장 의미 있는 title을 가진 행을 선택한다.
            # (예: 썸네일 a는 텍스트 없음, 제목 a는 텍스트 있음 — 후자가 이긴다)
            title = _clean_text(a.text(deep=True, strip=True)) or _clean_text(
                a.attributes.get("title") or ""
            )
            if not title:
                tr = _closest(a, "tr")
                if tr is not None:
                    title = _clean_text(tr.text(deep=True, strip=True))[:200]
            if not title:
                # 텍스트 없는 링크는 이번 항목으로 사용 안 하지만,
                # 같은 id의 다른 a가 뒤에 있으면 그게 잡히도록 seen에는 등록 안 함.
                continue

            if sid in seen:
                # 이미 잡힌 같은 id면 더 긴 title로 보정
                for it in items:
                    if it.source_id == sid and len(title) > len(it.title):
                        it.title = title
                continue
            seen.add(sid)

            detail_url = f"{BASE_URL}{DETAIL_PATH}?pblancId={sid}"
            items.append(
                ListingItem(
                    source_id=sid,
                    title=title,
                    detail_url=detail_url,
                    posting_status_hint="ONGOING",  # 메인 목록은 진행 중 위주
                )
            )
        return items


# ============================================================
# 모듈 헬퍼
# ============================================================
def _closest(node: Node, tag: str) -> Node | None:
    """selectolax에는 closest가 없으므로 수동 부모 추적."""
    cur = node.parent
    while cur is not None:
        if cur.tag == tag:
            return cur
        cur = cur.parent
    return None


def _clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _extract_period(html: str) -> str | None:
    """상세 HTML 본문에서 신청기간 라벨 다음 텍스트를 추출.

    G1: 라벨 다음에 2개 날짜(시작~종료)가 모두 있으면 함께 잡는다.
    1차는 DOM 기반 (라벨 셀 → 부모 행의 td/dd), 2차는 풀 텍스트 정규식.
    """
    tree = HTMLParser(html)

    # 1차: dt/th 라벨이 들어있는 부모 행에서 td/dd 셀 텍스트 직접 추출
    for label_node in tree.css("dt, th"):
        label_text = (label_node.text(deep=True, strip=True) or "")
        if "신청기간" not in label_text and "접수기간" not in label_text:
            continue
        # 부모 행 (tr / dl / div) 안의 모든 td/dd 셀
        row = _closest(label_node, "tr") or _closest(label_node, "dl") or label_node.parent
        if row is None:
            continue
        for cell in row.css("td, dd"):
            ctext = _clean_text(cell.text(deep=True, strip=True))
            if ctext and (
                re.search(r"\d{4}[.\-/]\d{1,2}", ctext)
                or re.search(r"상시|예산|마감", ctext)
            ):
                return ctext

    # 2차: 풀 텍스트 정규식 fallback
    text = tree.text(separator=" ", strip=True)
    m = _PERIOD_LABEL_RE.search(text)
    if not m:
        return None
    raw = _clean_text(m.group(1))
    return raw if len(raw) >= 5 else None
