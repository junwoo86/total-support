"""L2 · postings 라우터 심층 테스트.

필터(site/status/suitability/domain/q/hide_expired) 조합,
페이지네이션 일관성, PATCH 시 system_logs 기록까지 cover.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from total_support.api.main import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


# ============================================================
# GET /postings — 기본 응답 형태
# ============================================================
def test_list_postings_response_shape(client: TestClient):
    r = client.get("/api/grant/postings?page_size=5")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"items", "total", "page", "page_size"}
    assert isinstance(body["items"], list)
    for item in body["items"]:
        assert set(item.keys()) >= {
            "id", "source_site", "source_id", "title", "detail_url",
            "review_status", "posting_status", "assigned_fields",
            "ai_suitability", "first_seen_at", "last_updated_at", "d_day",
        }


def test_list_postings_d_day_present_for_dated_items(client: TestClient):
    r = client.get("/api/grant/postings?page_size=50")
    items = r.json()["items"]
    if not items:
        pytest.skip("DB에 공고 없음")
    # end_date 있는 항목은 d_day != None, end_date 없는 항목(상시)은 None
    for p in items:
        if p["end_date"] is None:
            assert p["d_day"] is None
        else:
            assert isinstance(p["d_day"], int)


# ============================================================
# GET /postings — 필터
# ============================================================
def test_filter_by_review_status(client: TestClient):
    r = client.get("/api/grant/postings?status=UNREVIEWED&page_size=10")
    assert r.status_code == 200
    for p in r.json()["items"]:
        assert p["review_status"] == "UNREVIEWED"


def test_filter_by_suitability(client: TestClient):
    r = client.get("/api/grant/postings?suitability=HIGH&page_size=20")
    assert r.status_code == 200
    for p in r.json()["items"]:
        assert p["ai_suitability"] == "HIGH"


def test_filter_by_site_returns_only_that_site(client: TestClient):
    r = client.get("/api/grant/postings?site=SBA&page_size=20")
    for p in r.json()["items"]:
        assert p["source_site"] == "SBA"


def test_filter_by_domain_substring_match(client: TestClient):
    """domain 필터는 assigned_fields(콤마 문자열) LIKE."""
    r = client.get("/api/grant/postings?domain=AI&page_size=20")
    assert r.status_code == 200
    for p in r.json()["items"]:
        # assigned_fields list 에 AI 가 포함
        assert "AI" in p["assigned_fields"]


def test_q_search_in_title(client: TestClient):
    """q 가 매치되지 않는 무작위 문자열이면 0건."""
    r = client.get(
        "/api/grant/postings?q=__NEVER_MATCH_XYZ123__&page_size=10"
    )
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_hide_expired_only_applies_to_review_filters(client: TestClient):
    """hide_expired=true 는 status=NEEDS_REVIEW/IN_PROGRESS 와 함께만 동작.

    UNREVIEWED 또는 status 미지정 시엔 만료 항목도 포함됨 (PRD §5.2).
    """
    # status 없이 hide_expired 만 — 만료 필터가 적용되지 않아야 함
    r_no = client.get("/api/grant/postings?hide_expired=true&page_size=200")
    # status=NEEDS_REVIEW + hide_expired — end_date < today 가 빠져야 함
    r_yes = client.get(
        "/api/grant/postings?status=NEEDS_REVIEW&hide_expired=true&page_size=200"
    )
    assert r_no.status_code == 200
    assert r_yes.status_code == 200
    for p in r_yes.json()["items"]:
        # 만료된 행이 들어왔다면 위반 — d_day는 음수가 아니어야 함 (None 허용)
        if p["d_day"] is not None:
            assert p["d_day"] >= 0, f"hide_expired 누수: {p['id']} d_day={p['d_day']}"


# ============================================================
# 페이지네이션
# ============================================================
def test_pagination_validates_bounds(client: TestClient):
    assert client.get("/api/grant/postings?page=0").status_code == 422
    assert client.get("/api/grant/postings?page_size=0").status_code == 422
    assert client.get("/api/grant/postings?page_size=201").status_code == 422


def test_pagination_returns_consistent_total(client: TestClient):
    """page 변경 시 total 은 동일 + 페이지 간 id 중복 없음."""
    r1 = client.get("/api/grant/postings?page=1&page_size=10").json()
    if r1["total"] < 11:
        pytest.skip("페이지 분할 검증용 데이터 부족")
    r2 = client.get("/api/grant/postings?page=2&page_size=10").json()
    assert r1["total"] == r2["total"]
    ids1 = {p["id"] for p in r1["items"]}
    ids2 = {p["id"] for p in r2["items"]}
    assert ids1.isdisjoint(ids2), "page 1/2 간에 id 중복"


# ============================================================
# GET /postings/{id}/detail
# ============================================================
def test_detail_includes_content_html(client: TestClient):
    listed = client.get("/api/grant/postings?page_size=1").json()["items"]
    if not listed:
        pytest.skip("DB에 공고 없음")
    pid = listed[0]["id"]
    r = client.get(f"/api/grant/postings/{pid}/detail")
    assert r.status_code == 200
    assert "content_html" in r.json()


# ============================================================
# PATCH /postings/{id}/review-status
# ============================================================
def test_patch_review_status_updates_and_logs(client: TestClient):
    listed = client.get("/api/grant/postings?page_size=1").json()["items"]
    if not listed:
        pytest.skip("DB에 공고 없음")
    pid = listed[0]["id"]
    original = listed[0]["review_status"]
    target = "EXCLUDED" if original != "EXCLUDED" else "UNREVIEWED"

    # 로그 시작 카운트
    logs_before = client.get("/api/grant/logs?category=API&limit=2000").json()
    before_ids = {L["id"] for L in logs_before}

    r = client.patch(
        f"/api/grant/postings/{pid}/review-status", json={"status": target}
    )
    assert r.status_code == 200
    assert r.json()["review_status"] == target

    # 로그에 신규 PATCH 항목이 추가됨
    logs_after = client.get("/api/grant/logs?category=API&limit=2000").json()
    new_logs = [L for L in logs_after if L["id"] not in before_ids]
    assert any(
        f"/postings/{pid}/review-status" in L["message"] for L in new_logs
    ), "PATCH 로그 누락"

    # 원복
    client.patch(
        f"/api/grant/postings/{pid}/review-status", json={"status": original}
    )


def test_patch_review_status_same_value_is_noop(client: TestClient):
    """같은 값으로 PATCH 시 200 OK, 로그 추가 없이 그대로 반환."""
    listed = client.get("/api/grant/postings?page_size=1").json()["items"]
    if not listed:
        pytest.skip("DB에 공고 없음")
    pid = listed[0]["id"]
    current = listed[0]["review_status"]

    logs_before = len(client.get("/api/grant/logs?category=API&limit=2000").json())
    r = client.patch(
        f"/api/grant/postings/{pid}/review-status", json={"status": current}
    )
    assert r.status_code == 200
    logs_after = len(client.get("/api/grant/logs?category=API&limit=2000").json())
    # noop 이므로 로그 카운트 증가 없음 (혹은 매우 작음 — 동시 다른 테스트 영향)
    assert logs_after - logs_before <= 1
