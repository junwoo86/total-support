"""SBA 파싱 단위 테스트 — Playwright 없이 HTML 픽스처."""

from __future__ import annotations

from total_support.scrapers.sba import _extract_detail_period, _rows_to_items

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
    from total_support.scrapers.sba import _MID_RE
    m = _MID_RE.search("/PostingDetail.aspx?p=0&mid=91b23d38-5953-f111-b404-d4f5ef4a1e33")
    assert m is not None
    assert m.group(1) == "91b23d38-5953-f111-b404-d4f5ef4a1e33"


# ============================================================
# _rows_to_items — list 페이지 후처리 회귀 가드
# (브라우저 JS 추출 결과 → ListingItem 변환부)
# ============================================================
def _row(**kw):
    return {"mid": "", "title": "", "start": "", "end": "", **kw}


def test_rows_to_items_real_sba_example():
    """실측 SBA OngoingList row: a 태그 텍스트가 사업명, td 텍스트는 placeholder."""
    rows = [
        _row(
            mid="a19630f6-9955-f111-b404-d4f5ef4a1e33",
            title="2026 서울콘 아트홀 프로그램 협력사 모집",
            start="2026-05-22",
            end="2026-06-01",
        ),
        _row(
            mid="213ba8a4-2154-f111-b404-d4f5ef4a1e33",
            title="2026년 칠레(메르카도리브레) 온라인 시장 진출 지원사업 참여기업 2차 모집",
            start="2026-05-21",
            end="2026-06-04",
        ),
    ]
    items = _rows_to_items(rows, posting_status="ONGOING", seen_mids=set())
    assert len(items) == 2
    assert items[0].source_id == "a19630f6-9955-f111-b404-d4f5ef4a1e33"
    assert items[0].title == "2026 서울콘 아트홀 프로그램 협력사 모집"
    assert items[0].raw_period_hint == "2026-05-22 ~ 2026-06-01"
    assert items[0].posting_status_hint == "ONGOING"
    assert items[0].detail_url.endswith("&mid=a19630f6-9955-f111-b404-d4f5ef4a1e33")
    assert items[1].raw_period_hint == "2026-05-21 ~ 2026-06-04"


def test_rows_to_items_rejects_placeholder_titles():
    """회귀 가드: title이 비거나 너무 짧으면 적재 금지.

    이전 버그: '접수일정 표시란(시작일 ~ 종료일) ...' 같은 폼 라벨이
    title로 채택되어 적재됨. 새 추출기는 `<a>` 텍스트만 사용하므로
    a 태그가 없는 row(=placeholder만 있는 row)는 mid 가 있어도 스킵.
    """
    rows = [
        _row(mid="dead-beef-1111-2222-333344445555", title=""),
        _row(mid="dead-beef-1111-2222-666677778888", title="x"),  # 너무 짧음
    ]
    items = _rows_to_items(rows, posting_status="ONGOING", seen_mids=set())
    assert items == []


def test_rows_to_items_dedupes_via_seen_mids():
    seen: set[str] = set()
    rows1 = [_row(mid="aaaaaaaa-1111-2222-3333-444444444444", title="사업 A",
                  start="2026-01-01", end="2026-01-31")]
    rows2 = [_row(mid="aaaaaaaa-1111-2222-3333-444444444444", title="사업 A 중복",
                  start="2026-01-01", end="2026-01-31")]
    items1 = _rows_to_items(rows1, "ONGOING", seen)
    items2 = _rows_to_items(rows2, "ONGOING", seen)
    assert len(items1) == 1
    assert items2 == []  # 두 번째 호출은 같은 mid → 스킵


def test_rows_to_items_period_hint_optional():
    """접수기간 정보 없는 row 도 적재는 되되 hint=None (상세 fetch로 백업 시도)."""
    rows = [_row(mid="bbbbbbbb-1111-2222-3333-444444444444",
                 title="기간 미상 사업")]
    items = _rows_to_items(rows, "SCHEDULED", set())
    assert len(items) == 1
    assert items[0].raw_period_hint is None
    assert items[0].posting_status_hint == "SCHEDULED"
