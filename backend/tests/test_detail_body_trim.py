"""postings._trim_body_html — 저장된 raw content_html 의 본문 selector 후추출.

옵션 A: 첫 풀 수집 시점에 selector 가 fetch_detail 에 적용되기 전이라
모든 row 의 content_html 이 페이지 전체로 저장됨. 이 함수가 detail
응답 시점에 한 번 더 selector 를 시도해 모달에 본문만 노출한다.
"""

from __future__ import annotations

import pytest

from total_support.services.postings import _trim_body_html


# ============================================================
# 매치 성공 (구 데이터 = 전체 페이지)
# ============================================================
def test_bizinfo_view_cont_extracted_from_full_page():
    body = "사업 개요 핵심 본문 텍스트 " * 10  # 50자 이상
    html = f"""
    <body>
      <header>기업마당 메뉴 노이즈</header>
      <div class="sub_cont"><div class="view_cont">{body}</div></div>
      <footer>관련 사업 푸터</footer>
    </body>
    """
    out = _trim_body_html("BIZINFO", html)
    assert "view_cont" in out
    assert "메뉴 노이즈" not in out
    assert "관련 사업 푸터" not in out
    assert "핵심 본문" in out


def test_iris_content_extracted():
    body = "공고 본문 내용 " * 10
    html = f"""<body>
      <div class="header">IRIS 네비게이션 메뉴</div>
      <div id="content">{body}</div>
      <div class="footer">사이트 푸터</div>
    </body>"""
    out = _trim_body_html("IRIS", html)
    assert "content" in out or "공고 본문" in out
    assert "네비게이션" not in out
    assert "사이트 푸터" not in out


def test_sba_rignt_content_typo_selector_works():
    """SBA 사이트 원본 ID 가 'rignt_content' (typo) — selector 도 그대로 매칭."""
    body = "SBA 본문 내용 " * 10
    html = f"""<body>
      <div id="container">
        <div id="rignt_content">{body}</div>
      </div>
    </body>"""
    out = _trim_body_html("SBA", html)
    assert "rignt_content" in out
    assert "SBA 본문" in out


# ============================================================
# Fallback path
# ============================================================
def test_unknown_site_returns_original():
    html = "<div>any content</div>"
    assert _trim_body_html("NAVER", html) == html


def test_none_or_empty_html_passthrough():
    assert _trim_body_html("BIZINFO", None) is None
    assert _trim_body_html("BIZINFO", "") == ""


def test_no_selector_match_returns_original():
    """selector 없는 마크업 — 원본 그대로 (모달에 raw 노출)."""
    html = "<body><div>본문 컨테이너가 다른 마크업으로 변경된 경우</div></body>"
    out = _trim_body_html("BIZINFO", html)
    assert out == html


def test_too_short_match_falls_through_to_fallback():
    """selector 가 잡혔지만 50자 미만이면 의미 없는 영역 → fallback selector 또는 원본."""
    html = """<body>
      <div class="view_cont">짧음</div>
      <div class="sub_cont">충분히 긴 본문 영역 — 50자 이상이어야 합니다. 추가 텍스트 ㅎㅎ</div>
    </body>"""
    out = _trim_body_html("BIZINFO", html)
    assert "충분히 긴 본문" in out  # fallback sub_cont 가 잡혀야 함


def test_invalid_html_does_not_crash():
    out = _trim_body_html("BIZINFO", "not html at all <<<")
    assert isinstance(out, str)  # 원본 그대로


# ============================================================
# Idempotent 보장 — 신 데이터(이미 trim 된 fragment)
# ============================================================
def test_already_trimmed_fragment_idempotent():
    """이미 본문만 잘린 fragment 가 들어와도 같은 selector 가 매치되거나
    매치 실패 시 원본 그대로 — 절대 더 작아지지 않는다."""
    body = "본문 충분히 긴 텍스트 " * 10
    trimmed = f'<div class="view_cont">{body}</div>'
    out = _trim_body_html("BIZINFO", trimmed)
    # selector 매치 → 자기 자신, 또는 fragment 그대로
    assert "본문 충분히 긴 텍스트" in out
    assert len(out) >= len(body)
