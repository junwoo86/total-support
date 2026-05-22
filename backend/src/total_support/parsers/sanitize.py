"""HTML sanitize — PRD §4.2 content_html 저장 전 정화.

규칙:
- `<script>`, `<iframe>` 완전 제거 (태그+내용)
- 인라인 이벤트 핸들러(`onclick`, `onload`, …) 모두 속성 제거
- 외부 이미지는 `src` 유지 (PRD가 명시적으로 허용)
- 안전한 태그/속성은 보존하여 사이트 본문 시각을 유지
- `style` 속성은 제거 (XSS · 디자인 시스템 일관성 양쪽 이유)

이중 방어: 프론트 렌더링 시 `iframe sandbox`로 한 번 더 격리 (PRD §6.3-③).
"""

from __future__ import annotations

import re

import bleach

# bleach는 비허용 태그를 strip할 때 태그만 제거하고 내용은 텍스트로 남긴다.
# PRD §4.2의 의도는 `<script>`/`<iframe>` 전체 제거이므로 사전에 정규식으로
# 블록을 통째 제거한다. multiline=True, dot 매치 줄바꿈 포함.
_DANGEROUS_BLOCK_RE = re.compile(
    r"<(script|iframe|object|embed|svg|math|style)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
# self-closing 또는 닫는 태그 누락 케이스 — 시작 태그만 있는 위험 태그 단독 제거
_DANGEROUS_LONE_RE = re.compile(
    r"<(script|iframe|object|embed|svg|math|style)\b[^>]*/?>",
    re.IGNORECASE,
)

# ============================================================
# 보존 화이트리스트
# ============================================================

# 공고 본문에서 합리적으로 사용되는 태그만 허용
ALLOWED_TAGS = {
    # 텍스트 블록
    "h1", "h2", "h3", "h4", "h5", "h6",
    "p", "div", "span", "br", "hr",
    "blockquote", "pre", "code",
    # 인라인 강조
    "strong", "b", "em", "i", "u", "s", "small", "sub", "sup", "mark",
    # 리스트
    "ul", "ol", "li", "dl", "dt", "dd",
    # 표
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    # 링크/이미지
    "a", "img", "figure", "figcaption",
}

# 태그별 허용 속성. PRD §4.2: 외부 이미지 src 유지.
ALLOWED_ATTRS = {
    "*": ["class", "id", "title", "lang"],
    "a": ["href", "rel", "target"],
    "img": ["src", "alt", "width", "height"],
    "th": ["scope", "colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
    "col": ["span"],
    "colgroup": ["span"],
}

# 링크 프로토콜 화이트리스트 — javascript:, data:는 차단
ALLOWED_PROTOCOLS = {"http", "https", "mailto"}


def sanitize_html(html: str | None) -> str:
    """공고 본문 HTML을 정화하여 안전한 형태로 반환.

    Args:
        html: 원본 HTML (None/빈 문자열이면 빈 문자열 반환).

    Returns:
        sanitize된 HTML. <script>/<iframe>/onclick 등 제거됨.
    """
    if not html:
        return ""

    # 1) 위험 태그 블록(내용 포함) 사전 제거 — bleach의 strip은 태그만 떼므로
    pre = _DANGEROUS_BLOCK_RE.sub("", html)
    pre = _DANGEROUS_LONE_RE.sub("", pre)

    # 2) 표준 sanitize
    cleaned = bleach.clean(
        pre,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        # strip=True: 비허용 태그를 통째로 제거 (내용은 유지하되 <script>는
        # 본문 자체가 위험하므로 strip_comments도 함께)
        strip=True,
        strip_comments=True,
    )

    # 외부 링크는 안전 속성 추가 (frontend가 신 탭으로 열 때 referrer 누수 방지)
    # bleach 자체로는 못 하므로 간단 후처리 — 정말 단순 패턴만 손댐.
    cleaned = cleaned.replace(
        '<a href="http', '<a target="_blank" rel="noopener noreferrer" href="http'
    )
    return cleaned
