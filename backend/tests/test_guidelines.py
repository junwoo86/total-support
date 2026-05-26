"""Company guideline 서비스 + API — version bump 및 백필 트리거 검증.

실제 LLM 호출은 mock. DB 는 live (다른 통합 테스트와 동일 환경).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from total_support.api.main import app
from total_support.db import SessionLocal
from total_support.services import guidelines as svc


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_guideline_after_each():
    """각 테스트 끝에 빈 지침으로 복원 — 다른 테스트 영향 방지."""
    yield
    with SessionLocal() as db:
        # _trigger_reevaluation_async 가 백그라운드 스레드를 띄울 수 있으니 patch
        with patch.object(svc, "_trigger_reevaluation_async", return_value=None):
            svc.update_content(db, content_md="")


# ============================================================
# GET /company-guideline
# ============================================================
def test_get_returns_default_empty_guideline(client):
    r = client.get("/api/grant/company-guideline")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == 1
    assert "content_md" in body
    assert isinstance(body["version"], int)


def test_get_creates_row_if_missing():
    """안전망: row 가 삭제되어도 get_current 가 자동 생성."""
    with SessionLocal() as db:
        # 직접 DELETE 후 get_current 호출
        from total_support.db import GrantCompanyGuideline
        row = db.get(GrantCompanyGuideline, 1)
        if row:
            db.delete(row)
            db.commit()
        recovered = svc.get_current(db)
        assert recovered.id == 1
        assert recovered.content_md == ""


# ============================================================
# PUT /company-guideline + version bump
# ============================================================
def test_put_bumps_version_and_triggers_backfill(client):
    initial = client.get("/api/grant/company-guideline").json()
    initial_version = initial["version"]

    with patch.object(svc, "_trigger_reevaluation_async") as mock_trigger:
        r = client.put(
            "/api/grant/company-guideline",
            json={"content_md": "우리 회사는 AI 의료 진단 솔루션 개발사입니다."},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["content_md"] == "우리 회사는 AI 의료 진단 솔루션 개발사입니다."
        assert body["version"] == initial_version + 1
        # 백필 트리거 호출 확인
        mock_trigger.assert_called_once_with(new_version=initial_version + 1)


def test_put_with_same_content_is_noop(client):
    # 사전 세팅 (백필 mocking)
    with patch.object(svc, "_trigger_reevaluation_async"):
        r1 = client.put(
            "/api/grant/company-guideline",
            json={"content_md": "동일 내용"},
        ).json()

    # 같은 내용으로 PUT — version 그대로
    with patch.object(svc, "_trigger_reevaluation_async") as mock_trigger:
        r2 = client.put(
            "/api/grant/company-guideline",
            json={"content_md": "동일 내용"},
        ).json()
        assert r2["version"] == r1["version"]
        mock_trigger.assert_not_called()


def test_put_strips_whitespace_for_diff_check(client):
    """앞뒤 공백 차이만 있으면 변경 없음으로 본다."""
    with patch.object(svc, "_trigger_reevaluation_async"):
        r1 = client.put(
            "/api/grant/company-guideline",
            json={"content_md": "내용 A"},
        ).json()

    with patch.object(svc, "_trigger_reevaluation_async") as mock_trigger:
        r2 = client.put(
            "/api/grant/company-guideline",
            json={"content_md": "   내용 A   \n"},
        ).json()
        assert r2["version"] == r1["version"]
        mock_trigger.assert_not_called()


# ============================================================
# get_current_guideline_for_eval — 평가 단계용 read 모델
# ============================================================
def test_for_eval_returns_none_when_empty(client):
    # 빈 지침 보장
    with patch.object(svc, "_trigger_reevaluation_async"):
        client.put("/api/grant/company-guideline", json={"content_md": ""})

    snap = svc.get_current_guideline_for_eval()
    assert snap is None


def test_for_eval_returns_snapshot_when_set(client):
    with patch.object(svc, "_trigger_reevaluation_async"):
        client.put(
            "/api/grant/company-guideline",
            json={"content_md": "회사 지침 본문"},
        )

    snap = svc.get_current_guideline_for_eval()
    assert snap is not None
    assert snap.content_md == "회사 지침 본문"
    assert snap.version >= 1


# ============================================================
# 입력 검증
# ============================================================
def test_put_rejects_overly_long_content(client):
    """schemas.CompanyGuidelinePut.max_length=10000 위반 → 422."""
    r = client.put(
        "/api/grant/company-guideline",
        json={"content_md": "x" * 10_001},
    )
    assert r.status_code == 422
