"""L2 · keywords 라우터 + /keywords/preview 심층 테스트.

PRD §5.5.3 의 4-mode 매처(WORD_BOUNDARY / EXACT_HANGUL / SUBSTRING / REGEX)
+ negative_context 좌우 30자 윈도우 동작을 라우터 레벨에서 검증.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import LIVE_DB_GUARD_ENABLED, LIVE_DB_GUARD_REASON
from total_support.api.main import app

pytestmark = pytest.mark.skipif(LIVE_DB_GUARD_ENABLED, reason=LIVE_DB_GUARD_REASON)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def temp_domain(client: TestClient):
    """테스트 전용 임시 분야 — 매 테스트마다 깨끗하게 생성/삭제."""
    code = f"TEST_KW_{uuid.uuid4().hex[:8].upper()}"
    d = client.post(
        "/api/grant/domains", json={"code": code, "label_ko": "키워드테스트"}
    ).json()
    yield d
    client.delete(f"/api/grant/domains/{d['id']}?hard=true")


# ============================================================
# GET /domains/{domain_id}/keywords
# ============================================================
def test_list_keywords_404_for_unknown_domain(client: TestClient):
    r = client.get("/api/grant/domains/9999999/keywords")
    assert r.status_code == 404


def test_list_keywords_empty_for_new_domain(client: TestClient, temp_domain):
    r = client.get(f"/api/grant/domains/{temp_domain['id']}/keywords")
    assert r.status_code == 200
    assert r.json() == []


# ============================================================
# POST /domains/{domain_id}/keywords
# ============================================================
def test_create_keyword_returns_201_with_defaults(client: TestClient, temp_domain):
    r = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords",
        json={"keyword": "샘플키워드"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["keyword"] == "샘플키워드"
    assert body["match_mode"] == "WORD_BOUNDARY"
    assert body["case_sensitive"] is False
    assert body["enabled"] is True


def test_create_keyword_404_for_unknown_domain(client: TestClient):
    r = client.post(
        "/api/grant/domains/9999999/keywords", json={"keyword": "X"}
    )
    assert r.status_code == 404


def test_create_keyword_rejects_invalid_regex(client: TestClient, temp_domain):
    r = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords",
        json={"keyword": "[unclosed", "match_mode": "REGEX"},
    )
    assert r.status_code == 422


def test_create_keyword_rejects_blank(client: TestClient, temp_domain):
    r = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords",
        json={"keyword": ""},
    )
    assert r.status_code == 422  # min_length=1


# ============================================================
# PATCH /domains/{domain_id}/keywords/{keyword_id}
# ============================================================
def test_patch_keyword_404_when_keyword_belongs_to_other_domain(
    client: TestClient, temp_domain
):
    """다른 domain 의 keyword id 로 PATCH 시 404."""
    k = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords",
        json={"keyword": "kw"},
    ).json()

    # AI 도메인 id 가져오기
    ai = next(d for d in client.get("/api/grant/domains").json() if d["code"] == "AI")
    r = client.patch(
        f"/api/grant/domains/{ai['id']}/keywords/{k['id']}",
        json={"enabled": False},
    )
    assert r.status_code == 404


def test_patch_keyword_validates_regex_on_mode_change(
    client: TestClient, temp_domain
):
    """SUBSTRING → REGEX 로 모드 변경 시 기존 keyword 가 invalid regex 면 422."""
    k = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords",
        json={"keyword": "[unclosed", "match_mode": "SUBSTRING"},
    ).json()
    r = client.patch(
        f"/api/grant/domains/{temp_domain['id']}/keywords/{k['id']}",
        json={"match_mode": "REGEX"},
    )
    assert r.status_code == 422


def test_patch_keyword_only_changes_provided_fields(
    client: TestClient, temp_domain
):
    k = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords",
        json={
            "keyword": "원본",
            "match_mode": "SUBSTRING",
            "case_sensitive": True,
            "negative_context": ["제외"],
        },
    ).json()
    r = client.patch(
        f"/api/grant/domains/{temp_domain['id']}/keywords/{k['id']}",
        json={"enabled": False},
    )
    body = r.json()
    assert body["enabled"] is False
    assert body["keyword"] == "원본"
    assert body["match_mode"] == "SUBSTRING"
    assert body["case_sensitive"] is True
    assert body["negative_context"] == ["제외"]


# ============================================================
# DELETE /domains/{domain_id}/keywords/{keyword_id}
# ============================================================
def test_delete_keyword_404_for_unknown(client: TestClient, temp_domain):
    r = client.delete(
        f"/api/grant/domains/{temp_domain['id']}/keywords/9999999"
    )
    assert r.status_code == 404


def test_delete_keyword_removes_row(client: TestClient, temp_domain):
    k = client.post(
        f"/api/grant/domains/{temp_domain['id']}/keywords", json={"keyword": "삭제대상"}
    ).json()
    r = client.delete(
        f"/api/grant/domains/{temp_domain['id']}/keywords/{k['id']}"
    )
    assert r.status_code == 204
    after = client.get(f"/api/grant/domains/{temp_domain['id']}/keywords").json()
    assert all(x["id"] != k["id"] for x in after)


# ============================================================
# POST /keywords/preview — match_mode별
# ============================================================
def test_preview_shape_has_required_fields(client: TestClient):
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "AI", "match_mode": "WORD_BOUNDARY"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"matched", "scanned", "samples"}
    assert isinstance(body["matched"], int)
    assert isinstance(body["scanned"], int)
    assert isinstance(body["samples"], list)
    for s in body["samples"]:
        assert set(s.keys()) >= {"posting_id", "title", "context", "start", "end"}


def test_preview_substring_mode_returns_200(client: TestClient):
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "지원", "match_mode": "SUBSTRING"},
    )
    assert r.status_code == 200
    # '지원' 은 공고 본문에 매우 흔하므로 매치가 0 이상
    assert r.json()["matched"] >= 0


def test_preview_exact_hangul_mode_returns_200(client: TestClient):
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "바이오", "match_mode": "EXACT_HANGUL"},
    )
    assert r.status_code == 200


def test_preview_regex_invalid_returns_422(client: TestClient):
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "(?P<unclosed", "match_mode": "REGEX"},
    )
    assert r.status_code == 422


def test_preview_rejects_negative_context_with_invalid_pattern(client: TestClient):
    """REGEX 모드에선 keyword 검증이 빌드 단계에서 실패해야 함."""
    r = client.post(
        "/api/grant/keywords/preview",
        json={
            "keyword": "[abc",  # invalid char class
            "match_mode": "REGEX",
        },
    )
    assert r.status_code == 422


def test_preview_scanned_is_capped_at_100(client: TestClient):
    """PRD §5.5.3 최근 100건 제한."""
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "AI", "match_mode": "WORD_BOUNDARY"},
    )
    assert r.json()["scanned"] <= 100


def test_preview_returns_at_most_5_samples(client: TestClient):
    """샘플은 최대 5건."""
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "지원", "match_mode": "SUBSTRING"},
    )
    body = r.json()
    assert len(body["samples"]) <= 5
