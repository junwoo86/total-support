"""BIZINFO 파싱 테스트 — 네트워크 없이 HTML 픽스처로 검증."""

from __future__ import annotations

from total_support.scrapers.bizinfo import BizinfoScraper, _extract_period


def test_parse_list_extracts_pblanc_ids():
    """목록 HTML에서 pblancId 기반 a 태그를 모두 잡는다."""
    html = """
    <table>
      <tr><td><a href="/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122322">
        충청북도 바이오 글로벌 임상</a></td></tr>
      <tr><td><a href="/sii/siia/selectSIIA200Detail.do?pblancId=PBLN_000000000122401">
        상시 모집 — 웰니스 시제품 바우처</a></td></tr>
      <tr><td><a href="/some/other/page.do?id=irrelevant">관계없는 링크</a></td></tr>
    </table>
    """
    scraper = BizinfoScraper()
    try:
        items = scraper._parse_list(html)
    finally:
        scraper.close()

    assert len(items) == 2
    ids = {i.source_id for i in items}
    assert ids == {"PBLN_000000000122322", "PBLN_000000000122401"}
    assert all(i.detail_url.endswith(f"?pblancId={i.source_id}") for i in items)
    assert "충청북도" in items[0].title or "충청북도" in items[1].title


def test_parse_list_dedupes_same_id():
    """같은 pblancId가 여러 a 태그(썸네일+제목)로 노출돼도 1행만."""
    html = """
    <div>
      <a href="/x?pblancId=PBLN_000000000122322"><img alt="썸네일"></a>
      <a href="/x?pblancId=PBLN_000000000122322">사업 상세</a>
    </div>
    """
    scraper = BizinfoScraper()
    try:
        items = scraper._parse_list(html)
    finally:
        scraper.close()
    assert len(items) == 1


def test_parse_list_handles_empty():
    scraper = BizinfoScraper()
    try:
        assert scraper._parse_list("<html><body></body></html>") == []
    finally:
        scraper.close()


def test_extract_period_finds_label():
    html = """
    <div>
      <dt>신청기간</dt>
      <dd>2026.05.20 ~ 2026.06.08</dd>
    </div>
    """
    out = _extract_period(html)
    assert out is not None
    assert "2026.05.20" in out
    assert "2026.06.08" in out


def test_extract_period_returns_none_when_missing():
    html = "<p>접수기간 항목이 없는 본문</p>"
    assert _extract_period(html) is None


def test_extract_period_full_range_with_weekday_g1():
    """G1: 양쪽 날짜 모두 캡처 — 요일 부속까지."""
    html = """
    <table><tr>
      <th>신청기간</th>
      <td>2026.05.21(목) ~ 2026.06.30(화) 18:00 까지</td>
    </tr></table>
    """
    out = _extract_period(html)
    assert out is not None
    # 종료일까지 함께 캡처되어야 함
    assert "2026.05.21" in out
    assert ("2026.06.30" in out) or ("06.30" in out)


def test_extract_period_short_end_year_omitted_g1():
    """G1: 'YYYY.MM.DD ~ MM.DD' 단편형도 캡처."""
    html = """
    <dt>접수기간</dt>
    <dd>2026.05.21 ~ 06.30</dd>
    """
    out = _extract_period(html)
    assert out is not None
    assert "2026.05.21" in out
    assert "06.30" in out
