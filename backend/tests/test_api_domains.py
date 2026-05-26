"""L2 · domains 라우터 심층 테스트.

test_api_integration.py 의 스모크 흐름을 보완해 라우터의
모든 분기(중복/404/cascade/필터)와 스키마 validator 분기를 cover.
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


def _unique_code(prefix: str = "TEST_D") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8].upper()}"


def _cleanup(client: TestClient, code: str) -> None:
    """해당 code 의 잔여 row 를 hard-delete (멱등)."""
    for d in client.get("/api/grant/domains").json():
        if d["code"] == code:
            client.delete(f"/api/grant/domains/{d['id']}?hard=true")


# ============================================================
# GET /domains — 목록 + include_disabled
# ============================================================
def test_list_domains_default_includes_disabled(client: TestClient):
    """include_disabled 기본 True — 비활성화된 분야도 응답에 포함."""
    code = _unique_code("INC")
    _cleanup(client, code)
    r = client.post("/api/grant/domains", json={"code": code, "label_ko": "포함체크"})
    new_id = r.json()["id"]
    client.delete(f"/api/grant/domains/{new_id}")  # soft-delete

    rows = client.get("/api/grant/domains").json()
    assert any(d["id"] == new_id and d["enabled"] is False for d in rows)

    rows = client.get("/api/grant/domains?include_disabled=false").json()
    assert all(d["id"] != new_id for d in rows)

    _cleanup(client, code)


def test_list_domains_ordered_by_display_order_then_id(client: TestClient):
    rows = client.get("/api/grant/domains").json()
    # display_order ASC NULLS LAST, then id
    keyed = [(d.get("display_order"), d["id"]) for d in rows]
    has_order = [k for k in keyed if k[0] is not None]
    assert has_order == sorted(has_order, key=lambda x: (x[0], x[1])), (
        f"display_order 정렬 위반: {has_order}"
    )


# ============================================================
# POST /domains — 검증 분기
# ============================================================
def test_create_domain_rejects_blank_code(client: TestClient):
    r = client.post("/api/grant/domains", json={"code": "", "label_ko": "공백"})
    assert r.status_code == 422  # min_length=1


def test_create_domain_rejects_invalid_color(client: TestClient):
    r = client.post(
        "/api/grant/domains",
        json={"code": _unique_code(), "label_ko": "라벨", "color": "red"},
    )
    assert r.status_code == 422  # pattern=^#[0-9a-fA-F]{6}$


def test_create_domain_rejects_long_label(client: TestClient):
    r = client.post(
        "/api/grant/domains",
        json={"code": _unique_code(), "label_ko": "가" * 41},
    )
    assert r.status_code == 422  # max_length=40


def test_create_domain_duplicate_code_returns_409(client: TestClient):
    """code UNIQUE 제약 위반 → IntegrityError → 409 변환."""
    code = _unique_code("DUP")
    _cleanup(client, code)
    r = client.post("/api/grant/domains", json={"code": code, "label_ko": "첫번째"})
    assert r.status_code == 201

    r2 = client.post("/api/grant/domains", json={"code": code, "label_ko": "두번째"})
    assert r2.status_code == 409
    assert "중복" in r2.json()["detail"] or "duplicate" in r2.json()["detail"].lower()

    _cleanup(client, code)


# ============================================================
# PATCH /domains/{id}
# ============================================================
def test_patch_domain_404_for_unknown_id(client: TestClient):
    r = client.patch("/api/grant/domains/9999999", json={"label_ko": "X"})
    assert r.status_code == 404


def test_patch_domain_partial_does_not_touch_other_fields(client: TestClient):
    code = _unique_code("PARTIAL")
    _cleanup(client, code)
    created = client.post(
        "/api/grant/domains",
        json={"code": code, "label_ko": "원본", "color": "#abcdef", "display_order": 5},
    ).json()

    r = client.patch(f"/api/grant/domains/{created['id']}", json={"label_ko": "수정"})
    assert r.status_code == 200
    body = r.json()
    assert body["label_ko"] == "수정"
    assert body["color"] == "#abcdef"  # 건드리지 않음
    assert body["display_order"] == 5

    _cleanup(client, code)


def test_patch_domain_rejects_invalid_color(client: TestClient):
    code = _unique_code("CLR")
    _cleanup(client, code)
    new_id = client.post(
        "/api/grant/domains", json={"code": code, "label_ko": "x"}
    ).json()["id"]

    r = client.patch(f"/api/grant/domains/{new_id}", json={"color": "not-a-color"})
    assert r.status_code == 422

    _cleanup(client, code)


# ============================================================
# DELETE /domains/{id}
# ============================================================
def test_delete_domain_404_for_unknown(client: TestClient):
    r = client.delete("/api/grant/domains/9999999")
    assert r.status_code == 404


def test_hard_delete_cascades_to_keywords(client: TestClient):
    """hard=true 삭제 시 자식 키워드도 CASCADE."""
    code = _unique_code("CASCADE")
    _cleanup(client, code)
    d = client.post("/api/grant/domains", json={"code": code, "label_ko": "캐스케이드"}).json()

    # 자식 키워드 2개 생성
    k1 = client.post(
        f"/api/grant/domains/{d['id']}/keywords",
        json={"keyword": "kw_alpha", "match_mode": "SUBSTRING"},
    ).json()
    k2 = client.post(
        f"/api/grant/domains/{d['id']}/keywords",
        json={"keyword": "kw_beta", "match_mode": "SUBSTRING"},
    ).json()

    # 자식 존재 확인
    kws = client.get(f"/api/grant/domains/{d['id']}/keywords").json()
    assert {k1["id"], k2["id"]}.issubset({k["id"] for k in kws})

    # hard delete
    r = client.delete(f"/api/grant/domains/{d['id']}?hard=true")
    assert r.status_code == 204

    # 부모 없으면 자식 조회는 404 (domain not found)
    r = client.get(f"/api/grant/domains/{d['id']}/keywords")
    assert r.status_code == 404
