"""SBA 파싱 단위 테스트 — Playwright 없이 HTML 픽스처."""

from __future__ import annotations

from total_support.scrapers.sba import _extract_detail_period

# SbaScraper는 생성자에서 Playwright를 띄우므로 list parsing만 mock 형태로 검증.
# parse는 클래스 메서드라 분리된 헬퍼는 _extract_detail_period 정도뿐.


def test_extract_detail_period_dash():
    html = """
    <div>
      <th>접수기간</th>
      <td>2026-06-01 ~ 2026-06-27</td>
    </div>
    """
    out = _extract_detail_period(html)
    assert out is not None
    assert "2026-06-01" in out
    assert "2026-06-27" in out


def test_extract_detail_period_returns_none_when_missing():
    assert _extract_detail_period("<p>본문</p>") is None


def test_mid_guid_regex_matches_real_example():
    """PRD §2.1 실측 GUID 형식."""
    import re
    from total_support.scrapers.sba import _MID_RE
    m = _MID_RE.search("/PostingDetail.aspx?p=0&mid=91b23d38-5953-f111-b404-d4f5ef4a1e33")
    assert m is not None
    assert m.group(1) == "91b23d38-5953-f111-b404-d4f5ef4a1e33"
