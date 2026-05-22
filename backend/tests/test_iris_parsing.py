"""IRIS 파싱 단위 테스트 — 네트워크 없이 HTML 픽스처."""

from __future__ import annotations

from total_support.scrapers.iris import (
    IrisScraper,
    _extract_detail_period,
    _parse_total_page,
)


def test_parse_list_extracts_ancm_ids():
    html = """
    <table><tbody>
      <tr><td><a onclick="f_bsnsAncmBtinSituListForm_view('021878','ancmIng');return false">
        2026년도 바이오분야 인공지능 진단 모델 고도화 국책 과제 공고</a></td></tr>
      <tr><td><a onclick="f_bsnsAncmBtinSituListForm_view('021890','ancmIng');">
        디지털헬스 분야 의료기기 SaaS 상용화 R&D</a></td></tr>
      <tr><td><a onclick="f_bsnsAncmBtinSituListForm_view('019999','ancmEnd');">
        마감 공고 — 제외 대상</a></td></tr>
    </tbody></table>
    """
    s = IrisScraper()
    try:
        items = s._parse_list(html, ancmPrg="ancmIng", posting_status="ONGOING")
    finally:
        s.close()

    ids = {i.source_id for i in items}
    assert ids == {"021878", "021890"}  # ancmEnd 제외
    assert all(i.posting_status_hint == "ONGOING" for i in items)
    assert all("ancmId=" in i.detail_url for i in items)
    assert any("바이오분야" in i.title for i in items)


def test_parse_list_skips_ancmend_per_prd():
    html = """
    <a onclick="f_bsnsAncmBtinSituListForm_view('000111','ancmEnd');">마감</a>
    """
    s = IrisScraper()
    try:
        items = s._parse_list(html, ancmPrg="ancmIng", posting_status="ONGOING")
    finally:
        s.close()
    assert items == []


def test_parse_total_page():
    html = '<p class="page_info"><span id="totalPage">/ <b>6</b></span></p>'
    assert _parse_total_page(html) == 6

    # 없을 때 fallback
    assert _parse_total_page("<p>nothing</p>") == 1


def test_extract_detail_period_dash_format():
    """IRIS 실측: 2026-05-22 ~ 2026-06-22 형태."""
    html = """
    <div>
      <th>접수기간</th>
      <td>2026-05-22 ~ 2026-06-22</td>
    </div>
    """
    out = _extract_detail_period(html)
    assert out is not None
    assert "2026-05-22" in out
    assert "2026-06-22" in out


def test_extract_detail_period_with_weekday_and_time():
    """IRIS 실측: 2026.05.22(금) ~ 06.22(월) 18:00 까지."""
    html = """
    <div>
      <th>접수기간</th>
      <td>2026.05.22(금) ~ 06.22(월) 18:00 까지</td>
    </div>
    """
    out = _extract_detail_period(html)
    assert out is not None
    assert "2026.05.22" in out
    assert "06.22" in out
    assert "18:00" in out
