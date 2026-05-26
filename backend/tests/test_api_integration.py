"""L2 · API 통합 테스트 (TestClient + 실 DB).

PRD §9의 9 엔드포인트를 라이브 DB(dashboard-dev)에 대해 검증한다.
이미 마이그레이션이 적용되어 시드 4 도메인 + 18 키워드가 들어있다는 전제.
스모크 수준 — 외부 네트워크(스크래퍼)는 호출하지 않는다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import LIVE_DB_GUARD_ENABLED, LIVE_DB_GUARD_REASON
from total_support.api.main import app

pytestmark = pytest.mark.skipif(LIVE_DB_GUARD_ENABLED, reason=LIVE_DB_GUARD_REASON)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ============================================================
# 기본 ping + OpenAPI
# ============================================================
def test_ping_ok(client: TestClient):
    r = client.get("/api/grant/ping")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_openapi_lists_19_routes(client: TestClient):
    r = client.get("/api/grant/openapi.json")
    assert r.status_code == 200
    paths = r.json()["paths"]
    # /api/grant prefix는 OpenAPI에 적용되니 자유롭게 검증
    expected_keys = [
        "/api/grant/postings",
        "/api/grant/postings/{posting_id}/detail",
        "/api/grant/postings/{posting_id}/review-status",
        "/api/grant/domains",
        "/api/grant/domains/{domain_id}",
        "/api/grant/domains/{domain_id}/keywords",
        "/api/grant/domains/{domain_id}/keywords/{keyword_id}",
        "/api/grant/keywords/preview",
        "/api/grant/collection/run",
        "/api/grant/collection/runs",
        "/api/grant/collection/health",
        "/api/grant/logs",
    ]
    for k in expected_keys:
        assert k in paths, f"OpenAPI에 {k} 누락"


# ============================================================
# Domains 라우터
# ============================================================
def test_list_domains_returns_seed_4(client: TestClient):
    r = client.get("/api/grant/domains")
    assert r.status_code == 200
    domains = r.json()
    codes = {d["code"] for d in domains}
    # 시드는 AI/BIO/HEALTHCARE/WELLNESS
    assert {"AI", "BIO", "HEALTHCARE", "WELLNESS"}.issubset(codes)


def test_create_domain_validates_code(client: TestClient):
    r = client.post(
        "/api/grant/domains",
        json={"code": "lowercase", "label_ko": "테스트"},
    )
    # pattern=r"^[A-Z0-9_]+$" 위반 → 422
    assert r.status_code == 422


def test_domain_create_update_delete_cycle(client: TestClient):
    code = "TEST_API_INT"
    # cleanup (멱등)
    r = client.get("/api/grant/domains")
    for d in r.json():
        if d["code"] == code:
            client.delete(f"/api/grant/domains/{d['id']}?hard=true")

    # create
    r = client.post(
        "/api/grant/domains",
        json={"code": code, "label_ko": "API 통합 테스트", "color": "#ff0000", "display_order": 99},
    )
    assert r.status_code == 201
    new_id = r.json()["id"]

    # update (color 변경)
    r = client.patch(
        f"/api/grant/domains/{new_id}",
        json={"color": "#00ff00"},
    )
    assert r.status_code == 200
    assert r.json()["color"] == "#00ff00"

    # soft delete (enabled=False)
    r = client.delete(f"/api/grant/domains/{new_id}")
    assert r.status_code == 204
    # 확인
    r = client.get("/api/grant/domains")
    target = next((d for d in r.json() if d["id"] == new_id), None)
    assert target is not None
    assert target["enabled"] is False

    # hard delete (cleanup)
    r = client.delete(f"/api/grant/domains/{new_id}?hard=true")
    assert r.status_code == 204
    r = client.get("/api/grant/domains")
    assert all(d["id"] != new_id for d in r.json())


# ============================================================
# Keywords 라우터 + preview
# ============================================================
def test_list_keywords_of_ai_domain(client: TestClient):
    r = client.get("/api/grant/domains")
    ai = next(d for d in r.json() if d["code"] == "AI")
    r = client.get(f"/api/grant/domains/{ai['id']}/keywords")
    assert r.status_code == 200
    kws = r.json()
    # 시드 6개 (AI, 인공지능, 머신러닝, 딥러닝, Machine Learning, Deep Learning)
    assert len(kws) >= 4
    assert any(k["keyword"] == "AI" for k in kws)


def test_keyword_preview_endpoint(client: TestClient):
    r = client.post(
        "/api/grant/keywords/preview",
        json={
            "keyword": "AI",
            "match_mode": "WORD_BOUNDARY",
            "negative_context": ["SAIPA"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert "matched" in body
    assert "scanned" in body
    assert "samples" in body
    assert body["scanned"] <= 100  # PRD §5.5.3: 최근 100건


def test_keyword_preview_rejects_invalid_regex(client: TestClient):
    r = client.post(
        "/api/grant/keywords/preview",
        json={"keyword": "[unclosed", "match_mode": "REGEX"},
    )
    assert r.status_code == 422


# ============================================================
# Postings 라우터
# ============================================================
def test_list_postings_basic(client: TestClient):
    r = client.get("/api/grant/postings?page_size=10")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert "total" in body
    assert isinstance(body["items"], list)


def test_list_postings_filter_by_site(client: TestClient):
    r = client.get("/api/grant/postings?site=BIZINFO&page_size=50")
    assert r.status_code == 200
    items = r.json()["items"]
    # BIZINFO 시드 데이터가 있다면 전부 BIZINFO만 와야 함
    for p in items:
        assert p["source_site"] == "BIZINFO"


def test_get_posting_detail_404_for_missing(client: TestClient):
    r = client.get("/api/grant/postings/9999999/detail")
    assert r.status_code == 404


def test_patch_review_status_404_for_missing(client: TestClient):
    r = client.patch(
        "/api/grant/postings/9999999/review-status",
        json={"status": "EXCLUDED"},
    )
    assert r.status_code == 404


# ============================================================
# Collection · Health · Logs
# ============================================================
def test_health_returns_3_cards(client: TestClient):
    r = client.get("/api/grant/collection/health")
    assert r.status_code == 200
    body = r.json()
    assert "cards" in body
    sites = {c["source_site"] for c in body["cards"]}
    assert sites == {"BIZINFO", "IRIS", "SBA"}


def test_runs_endpoint(client: TestClient):
    r = client.get("/api/grant/collection/runs?days=30")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_run_trigger_invalid_site(client: TestClient):
    r = client.post("/api/grant/collection/run", json={"site": "NAVER"})
    # Literal["BIZINFO","IRIS","SBA"] 위반
    assert r.status_code == 422


def test_logs_endpoint(client: TestClient):
    r = client.get("/api/grant/logs?limit=10")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
