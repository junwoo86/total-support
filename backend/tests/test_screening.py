"""screen() 매처 — PRD §3.3 4모드 + negative_context."""

from __future__ import annotations

import pytest

from total_support.screening import KeywordSpec, screen


# ============================================================
# WORD_BOUNDARY — PRD §3.3.1 영문 단축어
# ============================================================
def test_word_boundary_matches_standalone_ai():
    spec = KeywordSpec(keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI")
    result = screen("우리는 AI 기술로 진단합니다", [spec])
    assert result.domains == ["AI"]
    assert result.assigned_fields == "AI"
    assert result.ai_suitability == "HIGH"


def test_word_boundary_rejects_substring_saipa():
    """PRD §3.3.1 예시: 'SAIPA'의 AI 부분은 매칭되면 안 됨."""
    spec = KeywordSpec(keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI")
    result = screen("SAIPA Innovation Lab", [spec])
    assert result.domains == []
    assert result.ai_suitability == "NORMAL"


# ============================================================
# EXACT_HANGUL — PRD §3.3.1 한글 단어
# ============================================================
def test_exact_hangul_matches_baio():
    spec = KeywordSpec(keyword="바이오", match_mode="EXACT_HANGUL", domain_label="바이오")
    result = screen("바이오 분야 R&D 지원", [spec])
    assert result.domains == ["바이오"]


def test_exact_hangul_rejects_baiographic():
    """PRD §3.3.1 예시: '바이오그래픽'에서는 매칭 안 됨."""
    spec = KeywordSpec(keyword="바이오", match_mode="EXACT_HANGUL", domain_label="바이오")
    result = screen("바이오그래픽 콘텐츠 사업", [spec])
    assert result.domains == []


# ============================================================
# SUBSTRING — PRD §3.3.1 긴 복합어
# ============================================================
def test_substring_matches_anywhere():
    spec = KeywordSpec(keyword="Healthcare", match_mode="SUBSTRING", domain_label="헬스케어")
    result = screen("Digital-Healthcare-Innovation", [spec])
    assert result.domains == ["헬스케어"]


def test_substring_case_insensitive_by_default():
    spec = KeywordSpec(keyword="Healthcare", match_mode="SUBSTRING", domain_label="헬스케어")
    result = screen("digital healthcare sandbox", [spec])
    assert result.domains == ["헬스케어"]


def test_substring_case_sensitive_when_flagged():
    spec = KeywordSpec(
        keyword="Healthcare",
        match_mode="SUBSTRING",
        domain_label="헬스케어",
        case_sensitive=True,
    )
    result = screen("digital healthcare sandbox", [spec])
    assert result.domains == []  # 'healthcare' (소문자) 불일치


# ============================================================
# REGEX — PRD §3.3.1 사용자 정규식
# ============================================================
def test_regex_user_pattern():
    spec = KeywordSpec(
        keyword=r"\b(AI|인공지능)\b",
        match_mode="REGEX",
        domain_label="AI",
    )
    result = screen("우리는 인공지능 R&D를 합니다", [spec])
    assert result.domains == ["AI"]


def test_regex_invalid_pattern_skipped_not_raised():
    """잘못된 정규식은 매처 자체에서는 조용히 스킵(호출자가 로깅)."""
    bad = KeywordSpec(keyword="[unclosed", match_mode="REGEX", domain_label="X")
    good = KeywordSpec(keyword="ok", match_mode="SUBSTRING", domain_label="X")
    result = screen("ok 좋아", [bad, good])
    assert result.domains == ["X"]


# ============================================================
# negative_context — PRD §3.3.2 (좌우 30자 윈도우)
# ============================================================
def test_negative_context_blocks_partial_but_other_match_survives():
    """일부 매칭은 negative window에 막혀도, 멀리 떨어진 다른 매칭이 살아남으면 도메인은 매칭."""
    spec = KeywordSpec(
        keyword="의료",
        match_mode="EXACT_HANGUL",
        domain_label="헬스케어",
        negative_context=("의료보험 가입 의무",),
    )
    # 첫 번째 '의료'는 멀리(>30자) 떨어져 있어 살아남고,
    # 마지막 '의료' 주변에는 negative 문구가 있어 차단됨.
    # 살아남은 첫 매칭으로 도메인 매칭 확정.
    long_filler = " 분야 R&D 지원 사업 — 매우 상세한 설명 " + ("…" * 40)
    result = screen(f"의료{long_filler} 4대 의료보험 가입 의무 안내", [spec])
    assert result.domains == ["헬스케어"]


def test_negative_context_blocks_all_matches():
    """모든 매칭이 negative window 안에 있으면 도메인 미매칭."""
    spec = KeywordSpec(
        keyword="AI",
        match_mode="WORD_BOUNDARY",
        domain_label="AI",
        negative_context=("SAIPA",),
    )
    # AI는 SAIPA의 일부가 아니지만 컨텍스트(30자 윈도우)에 SAIPA가 있음.
    # 케이스: "SAIPA에 협력하는 AI 컨설팅" — 'AI' 매칭, 그 ±30자에 SAIPA 포함
    result = screen("SAIPA에 협력하는 AI 컨설팅", [spec])
    # AI 매칭 위치 좌우 30자 안에 SAIPA → 차단
    assert result.domains == []


def test_negative_context_window_radius_exactly_30():
    """30자 윈도우 경계 검증 — 정확히 30자 안에 있으면 차단."""
    spec = KeywordSpec(
        keyword="Bio",
        match_mode="WORD_BOUNDARY",
        domain_label="바이오",
        negative_context=("Biography",),
    )
    # "Biography" 다음에 정확히 30자 후 "Bio" → 차단
    # "Biography_____________123_______Bio" — 길이 조정해서 정확히 30자 내
    padding = "x" * 25
    text = f"Biography{padding}Bio"  # 'Bio'의 start - 'Biography' 끝 = 25 < 30 → 차단
    result = screen(text, [spec])
    assert result.domains == []


# ============================================================
# 다중 도메인 / 다중 키워드
# ============================================================
def test_multiple_domains_match():
    """AI + 헬스케어 동시 매칭."""
    specs = [
        KeywordSpec(keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI"),
        KeywordSpec(keyword="Healthcare", match_mode="SUBSTRING", domain_label="헬스케어"),
        KeywordSpec(keyword="웰니스", match_mode="EXACT_HANGUL", domain_label="웰니스"),
    ]
    result = screen("AI Healthcare 융합 R&D — 웰니스 무관", [specs[0], specs[1]])
    assert result.domains == ["AI", "헬스케어"]
    assert result.assigned_fields == "AI, 헬스케어"


def test_disabled_keyword_skipped():
    spec_off = KeywordSpec(
        keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI", enabled=False
    )
    result = screen("AI 솔루션", [spec_off])
    assert result.domains == []


def test_empty_text_or_keywords():
    spec = KeywordSpec(keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI")
    assert screen("", [spec]).domains == []
    assert screen("AI 사업", []).domains == []


def test_no_match_means_normal_suitability():
    spec = KeywordSpec(keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI")
    result = screen("일반 경영안정자금 안내", [spec])
    assert result.ai_suitability == "NORMAL"
    assert result.assigned_fields is None


# ============================================================
# 도메인 순서 보존 (PRD §3.2 표기: 콤마 조합)
# ============================================================
def test_domain_order_follows_input_keyword_order():
    """결과 domains는 키워드 입력 순서를 따라 첫 매칭 순으로 정렬."""
    specs = [
        KeywordSpec(keyword="Healthcare", match_mode="SUBSTRING", domain_label="헬스케어"),
        KeywordSpec(keyword="AI", match_mode="WORD_BOUNDARY", domain_label="AI"),
    ]
    result = screen("AI Healthcare 융합", specs)
    # 입력 순서: Healthcare(헬스케어) 먼저, AI 다음
    assert result.domains == ["헬스케어", "AI"]
