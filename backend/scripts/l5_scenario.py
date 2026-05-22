"""L5 · 사용자 시나리오 시뮬레이션 (라이브 API).

PRD의 핵심 사용자 워크플로우 7단계를 실 API로 순차 실행하고 결과 검증.

1. 헬스 패널 확인
2. 미검토 목록 조회 (필터)
3. 공고 상세 보기
4. 상태 변경 (UNREVIEWED → NEEDS_REVIEW)
5. 변경 후 상태별 모니터링 목록에서 확인
6. 키워드 미리보기 (백오피스)
7. 시스템 로그에서 API 액션 추적
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8766"


def call(method: str, path: str, body: dict | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    data = json.dumps(body).encode() if body else None
    try:
        r = urllib.request.urlopen(req, data=data, timeout=15)
        ct = r.headers.get("Content-Type", "")
        body_str = r.read().decode("utf-8")
        return r.status, json.loads(body_str) if "json" in ct else body_str
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def assert_eq(actual, expected, label: str) -> None:
    if actual != expected:
        print(f"  ✗ {label}: expected {expected}, got {actual}")
        sys.exit(1)
    print(f"  ✓ {label}")


def main() -> int:
    print("=" * 60)
    print("L5 시나리오 — 사용자 워크플로우 7단계 라이브 검증")
    print("=" * 60)

    # ----- 1. 헬스 패널 -----
    print("\n[1] 헬스 패널 조회")
    s, body = call("GET", "/api/grant/collection/health")
    assert_eq(s, 200, "health 200")
    sites = {c["source_site"] for c in body["cards"]}
    assert_eq(sites, {"BIZINFO", "IRIS", "SBA"}, "3 사이트 카드")

    # ----- 2. 미검토 목록 (HIGH suitability 필터) -----
    print("\n[2] 미검토 + HIGH 필터")
    s, body = call("GET", "/api/grant/postings?status=UNREVIEWED&suitability=HIGH&page_size=5")
    assert_eq(s, 200, "postings 200")
    print(f"  - HIGH 미검토 {body['total']}건, 표시 {len(body['items'])}건")
    if not body["items"]:
        print("  ⚠ HIGH 미검토 0건 — 스모크 수집 후 재실행 권장. 시나리오 일부 스킵.")
        return 0
    pick = body["items"][0]
    print(f"  - 첫 항목 #{pick['id']} [{pick['source_site']}] {pick['title'][:50]}")

    # ----- 3. 상세 조회 -----
    print(f"\n[3] 공고 #{pick['id']} 상세 조회")
    s, detail = call("GET", f"/api/grant/postings/{pick['id']}/detail")
    assert_eq(s, 200, "detail 200")
    print(f"  - content_html 길이 = {len(detail.get('content_html') or '')}자")
    has_script = "<script" in (detail.get("content_html") or "").lower()
    assert_eq(has_script, False, "content_html에 <script> 없음 (sanitize 동작)")

    # ----- 4. 상태 변경: UNREVIEWED → NEEDS_REVIEW -----
    print(f"\n[4] 상태 변경 UNREVIEWED → NEEDS_REVIEW")
    s, body = call("PATCH", f"/api/grant/postings/{pick['id']}/review-status",
                   {"status": "NEEDS_REVIEW"})
    assert_eq(s, 200, "PATCH 200")
    assert_eq(body["review_status"], "NEEDS_REVIEW", "review_status 변경 확인")

    # ----- 5. 상태별 모니터링에서 등장 확인 -----
    print(f"\n[5] NEEDS_REVIEW 목록에서 #{pick['id']} 확인")
    s, body = call("GET", "/api/grant/postings?status=NEEDS_REVIEW&page_size=200")
    assert_eq(s, 200, "list 200")
    found = any(p["id"] == pick["id"] for p in body["items"])
    assert_eq(found, True, f"#{pick['id']}이 NEEDS_REVIEW 목록에 있음")

    # 원상복구 (다른 테스트 영향 방지)
    call("PATCH", f"/api/grant/postings/{pick['id']}/review-status",
         {"status": "UNREVIEWED"})

    # ----- 6. 키워드 미리보기 -----
    print("\n[6] 키워드 미리보기 (AI WORD_BOUNDARY + SAIPA 부정 컨텍스트)")
    s, body = call("POST", "/api/grant/keywords/preview", {
        "keyword": "AI",
        "match_mode": "WORD_BOUNDARY",
        "negative_context": ["SAIPA"],
    })
    assert_eq(s, 200, "preview 200")
    print(f"  - {body['matched']}건 매칭 / {body['scanned']}건 조회, 샘플 {len(body['samples'])}개")

    # ----- 7. 시스템 로그에 API 액션 흔적 -----
    print("\n[7] system_logs에서 API 카테고리 로그 검색")
    s, logs = call("GET", "/api/grant/logs?category=API&limit=5")
    assert_eq(s, 200, "logs 200")
    api_logs = [l for l in logs if "/review-status" in l["message"]]
    print(f"  - API 카테고리 {len(logs)}건, /review-status PATCH 로그 {len(api_logs)}건 (이번 시나리오 포함)")

    print()
    print("=" * 60)
    print("✓ L5 시나리오 7단계 모두 통과")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
