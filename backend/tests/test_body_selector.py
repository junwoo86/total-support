"""BaseScraper.extract_body_html — 본문 selector 추출 + 실패 카운터.

A 제안 (사이트별 본문 selector) 회귀 가드. Playwright 없이 BaseScraper 의
헬퍼만 직접 호출해서 검증한다.
"""

from __future__ import annotations

from collections.abc import Iterator

from total_support.scrapers.base import BaseScraper, ListingItem


# ============================================================
# 헬퍼: 실제 사이트 IO 없이 BaseScraper 만 인스턴스화하기 위한 stub
# ============================================================
class _StubScraper(BaseScraper):
    SITE_CODE = "BIZINFO"  # check_in 통과용
    BODY_SELECTORS = (".view_cont", ".sub_cont")

    def iter_listing_pages(self) -> Iterator[list[ListingItem]]:
        yield []

    def fetch_detail(self, item):
        return "<html></html>", None


def _scraper() -> _StubScraper:
    s = _StubScraper()
    s._body_selector_misses = []  # run() 가 normally 설정하는 attr 수동 주입
    return s


# ============================================================
# 본문 추출 성공 path
# ============================================================
def test_primary_selector_match_returns_only_body():
    body = "본문 핵심 내용 " * 10  # 50자 이상 (BODY_MIN_TEXT_LEN 통과)
    html = f"""
    <html><body>
      <div class="header">메뉴 헤더 — 노이즈 영역</div>
      <div class="view_cont"><h2>사업개요</h2><p>{body}</p></div>
      <div class="footer">관련 사업 다수 링크들 ...</div>
    </body></html>
    """
    out = _scraper().extract_body_html(html, source_id="ID1")
    assert "본문 핵심 내용" in out
    assert "메뉴 헤더" not in out
    assert "관련 사업" not in out


def test_fallback_selector_used_when_primary_missing():
    """primary(.view_cont) 없으면 fallback(.sub_cont) 사용."""
    html = """
    <html><body>
      <div class="sub_cont">사업 정보 페이지 헤더 + 본문이 함께 들어있는 영역으로
      길이는 충분히 깁니다. fallback 으로 잡혀야 합니다.</div>
    </body></html>
    """
    s = _scraper()
    out = s.extract_body_html(html, source_id="ID2")
    assert "사업 정보" in out
    # primary 가 잡혔으면 miss 카운터 0, fallback 으로 잡힌 거니까 miss 아님
    assert s._body_selector_misses == []


# ============================================================
# 실패 path (selector 깨짐 감지)
# ============================================================
def test_all_selectors_miss_records_warning_and_returns_full_html():
    html = "<html><body><div>본문 컨테이너가 변경된 새 마크업</div></body></html>"
    s = _scraper()
    out = s.extract_body_html(html, source_id="MISS_ID_001")
    # fallback to 전체 HTML
    assert "본문 컨테이너가 변경" in out
    # miss 누적
    assert s._body_selector_misses == ["MISS_ID_001"]


def test_too_short_body_ignored_then_fallback_or_miss():
    """selector 가 잡혔지만 내용이 50자 미만이면 의미 없는 영역으로 보고 무시."""
    html = """
    <html><body>
      <div class="view_cont">짧음</div>
      <div class="sub_cont">충분히 길어서 의미 있는 본문 영역 — 50자 이상이어야 합니다 ㅎㅎ</div>
    </body></html>
    """
    s = _scraper()
    out = s.extract_body_html(html, source_id="SHORT_ID")
    assert "충분히" in out  # fallback 으로 넘어가 sub_cont 선택


def test_no_selectors_configured_returns_input_unchanged():
    """BODY_SELECTORS 가 비면 (= 사이트가 정의 안 함) 그대로 통과."""
    class _Noop(BaseScraper):
        SITE_CODE = "IRIS"
        BODY_SELECTORS = ()
        def iter_listing_pages(self): yield []
        def fetch_detail(self, item): return "", None

    s = _Noop()
    s._body_selector_misses = []
    html = "<html><body>그대로</body></html>"
    assert s.extract_body_html(html, source_id="X") == html
    assert s._body_selector_misses == []


def test_invalid_html_does_not_crash():
    """selectolax 가 raise 해도 fallback. 스크래퍼 중단 X."""
    s = _scraper()
    out = s.extract_body_html("not html at all <<<", source_id="BAD")
    assert isinstance(out, str)
