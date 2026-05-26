"""pytest 설정 — src 경로 등록 + **운영 DB 절대 변경 금지** 가드.

핵심 정책 (2026-05-26 사용자 결정):
> "테스트 기능중에서 실제 DB 데이터를 건드는건 절대 하지않도록 전수조사 및 조치해줘.
>  복원이 문제가 아니라, 애초에 잠시라도 데이터가 수정되면 안돼."

채택한 방식 — **물리적 차단**:
  외부 트랜잭션 + SAVEPOINT rollback 패턴을 한 번 시도했으나 실패. 일부 코드 경로
  (Celery in-proc 잡 디스패치, 백그라운드 데몬 스레드 등)가 monkeypatch 된
  SessionLocal 을 우회해 자체 connection 으로 commit 했고, 그 결과 사용자 회사
  지침 본문이 두 번째로 손실됨 + tb_grant_postings 가 일시 변동함.

  ⇒ trade-off 보다 **안전**을 택함: 운영 DB 에 write 할 가능성이 있는 모든
  통합 테스트 파일은 환경변수 가드로 기본 SKIP. CI/일반 실행에선 read-only +
  순수 단위테스트만 동작. 운영 DB 와 분리된 테스트 PostgreSQL 을 띄운 사람만
  `TS_TEST_LIVE_DB=1` 로 enable.

영향 파일 (모두 파일 헤더에 `pytestmark = pytest.mark.skipif(...)` 적용됨):
  - test_l3_integration.py        : scraper.run() 실제 INSERT
  - test_api_domains.py            : POST/PATCH/DELETE
  - test_api_keywords.py           : POST/PATCH/DELETE + temp_domain
  - test_api_postings.py           : PATCH review-status
  - test_api_integration.py        : domain CRUD cycle
  - test_services.py               : 서비스 직접 commit
  - test_guidelines.py             : PUT + DELETE (이전 사고 원인)

안전 (영향 받지 않음):
  test_period.py · test_sanitize.py · test_iris_parsing.py ·
  test_bizinfo_parsing.py · test_sba_parsing.py · test_screening.py ·
  test_evaluator.py · test_body_selector.py · test_detail_body_trim.py ·
  test_enums.py · test_api_logs.py  ─ 순수 함수 / 읽기 전용
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_ROOT / "src"))


# 다른 파일들이 import 해서 marker 를 적용할 수 있도록 단일 출처로 export.
LIVE_DB_GUARD_REASON = (
    "운영 DB write 위험 — 별도 테스트 DB 가 준비된 환경에서만 "
    "TS_TEST_LIVE_DB=1 로 enable"
)
LIVE_DB_GUARD_ENABLED = os.getenv("TS_TEST_LIVE_DB") != "1"
