"""sanitize_html() — PRD §4.2 content_html 정화."""

from __future__ import annotations

from total_support.parsers.sanitize import sanitize_html


def test_strips_script_tag_completely():
    html = "<p>본문</p><script>alert(1)</script>"
    out = sanitize_html(html)
    assert "<script" not in out
    assert "alert(1)" not in out
    assert "<p>본문</p>" in out


def test_strips_iframe_completely():
    html = '<div>본문</div><iframe src="http://evil"></iframe>'
    out = sanitize_html(html)
    assert "<iframe" not in out
    assert "evil" not in out


def test_strips_inline_event_handlers():
    html = '<button onclick="hack()">눌러</button>'
    out = sanitize_html(html)
    assert "onclick" not in out
    # button 태그는 화이트리스트에 없으므로 strip되어 텍스트만 남음
    assert "눌러" in out


def test_preserves_external_image_src():
    """PRD §4.2: '외부 이미지는 src 유지'."""
    html = '<p>설명</p><img src="https://example.com/banner.png" alt="배너">'
    out = sanitize_html(html)
    assert 'src="https://example.com/banner.png"' in out
    assert 'alt="배너"' in out


def test_preserves_safe_table_structure():
    html = (
        "<table><thead><tr><th>항목</th></tr></thead>"
        "<tbody><tr><td>본문</td></tr></tbody></table>"
    )
    out = sanitize_html(html)
    assert "<table>" in out
    assert "<thead>" in out
    assert "<th>항목</th>" in out
    assert "<td>본문</td>" in out


def test_blocks_javascript_link_protocol():
    html = '<a href="javascript:alert(1)">click</a>'
    out = sanitize_html(html)
    # bleach가 href를 제거 (태그는 남길 수 있음)
    assert "javascript:" not in out


def test_links_get_noopener_for_external():
    html = '<a href="https://example.com">link</a>'
    out = sanitize_html(html)
    assert 'target="_blank"' in out
    assert "noopener" in out


def test_none_or_empty_returns_empty():
    assert sanitize_html(None) == ""
    assert sanitize_html("") == ""


def test_strips_style_attribute():
    html = '<p style="color:red">본문</p>'
    out = sanitize_html(html)
    assert "style=" not in out
    assert "본문" in out


def test_preserves_class_for_styling_hook():
    html = '<div class="callout">중요</div>'
    out = sanitize_html(html)
    assert 'class="callout"' in out
