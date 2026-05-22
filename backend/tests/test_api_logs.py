"""L2 · /logs 라우터 — 필터 + limit 검증."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from total_support.api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def test_list_logs_default_returns_array(client: TestClient):
    r = client.get("/api/grant/logs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_logs_response_item_shape(client: TestClient):
    rows = client.get("/api/grant/logs?limit=5").json()
    for L in rows:
        assert set(L.keys()) >= {
            "id", "created_at", "level", "category", "message"
        }


def test_logs_limit_validation_bounds(client: TestClient):
    assert client.get("/api/grant/logs?limit=0").status_code == 422
    assert client.get("/api/grant/logs?limit=2001").status_code == 422


def test_logs_limit_caps_result_size(client: TestClient):
    rows = client.get("/api/grant/logs?limit=3").json()
    assert len(rows) <= 3


def test_logs_filter_by_level(client: TestClient):
    rows = client.get("/api/grant/logs?level=INFO&limit=200").json()
    for L in rows:
        assert L["level"] == "INFO"


def test_logs_filter_by_category(client: TestClient):
    rows = client.get("/api/grant/logs?category=SCRAPER&limit=200").json()
    for L in rows:
        assert L["category"] == "SCRAPER"


def test_logs_filter_by_site(client: TestClient):
    rows = client.get("/api/grant/logs?site=BIZINFO&limit=200").json()
    for L in rows:
        assert L["source_site"] == "BIZINFO"


def test_logs_combined_filters(client: TestClient):
    """3개 필터 동시 — AND 조건."""
    rows = client.get(
        "/api/grant/logs?level=INFO&category=SCRAPER&site=BIZINFO&limit=50"
    ).json()
    for L in rows:
        assert L["level"] == "INFO"
        assert L["category"] == "SCRAPER"
        assert L["source_site"] == "BIZINFO"


def test_logs_ordered_desc_by_created_at(client: TestClient):
    rows = client.get("/api/grant/logs?limit=30").json()
    if len(rows) < 2:
        pytest.skip("로그 데이터 부족")
    timestamps = [L["created_at"] for L in rows]
    assert timestamps == sorted(timestamps, reverse=True), (
        "created_at DESC 정렬 위반"
    )
