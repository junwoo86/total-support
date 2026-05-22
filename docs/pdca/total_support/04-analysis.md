# PDCA · Check (Analyze) — Gap 분석

**대상**: PRD v9.0 (2026-05-22) vs Phase 0~10 구현 결과
**작성일**: 2026-05-22
**기준 산출물**: [backend/](../../../backend/) · [total_support_ui/](../../../total_support_ui/)

---

## A. 분석 범위 매트릭스

| PRD 섹션 | 요구사항 | 현재 상태 | 결론 |
|---|---|---|---|
| §1.3 운영 투명성 | 헬스 패널 + "지금 실행" + 마지막 OK 시각 | ✓ 백엔드 health API + 프론트 카드 | OK |
| §2.1 BIZINFO | httpx + cpage 순회 + pblancId | ✓ 라이브 1페이지 5건 적재 | OK (1 gap) |
| §2.1 IRIS | Form POST + ancmIng/Pre + ancmId 6자리 + 자체 상세뷰 | ✓ 코드 + 단위 테스트 | OK (라이브 검증 미실시) |
| §2.1 SBA | Playwright + __doPostBack + GUID + GET 상세 | ✓ 코드 | OK (라이브 검증 미실시) |
| §2.2 Early Break | 페이지 신규 0건 → break | ✓ `base.py:_process_page` 반환값 활용 | OK |
| §2.3 parse_period | P1~P6 우선순위 매트릭스 | ✓ 14개 테스트 통과 | OK |
| §2.4 collection_runs | 사이트별 run row 적재 | ✓ `base.py:run()` | OK |
| §3.1 시드 18 키워드 | AI/바이오/헬스케어/웰니스 | ✓ 마이그레이션 002 | OK |
| §3.3 screen 4모드 + neg_context | WORD_BOUNDARY/EXACT_HANGUL/SUBSTRING/REGEX | ✓ 19개 테스트 통과 | OK |
| §4 5 테이블 + CHECK 제약 | tb_grant_* 5종 | ✓ 라이브 DB 적재됨 | OK |
| §5.1 5탭 | 미검토/상태별/헬스/키워드/로그 | ✓ 프론트 구현 완료 | OK |
| §5.2 만료 자동 숨김 | end_date 비교 | ✓ 백엔드+프론트 양쪽 | OK |
| §5.3 D-Day | end_date - (now() AT TIME ZONE 'Asia/Seoul')::date | ✓ `dday_expr` | OK |
| §5.5 백오피스 마스터-디테일 | 분야 CRUD + 키워드 모달 | ✓ 프론트 + 백엔드 API | OK (LIVE 모드 preview 미연결) |
| §6.3-③ iframe sandbox | content_html 이중 방어 | ✗ dangerouslySetInnerHTML 그대로 | **GAP** |
| §7 데이터 시퀀스 | 트리거 → run → 파싱 → screen → upsert | ✓ `base.py` | OK |
| §8.1 system_logs | 5 카테고리 + 4 레벨 | ✓ `observability/logger.py` | OK |
| §8.2 백필 잡 | screened_with_version < latest | ✓ `screening/backfill.py` | OK (트리거 cron 미설정) |
| §8.3 FAIL 알림 + 36h stale | Slack/Email | ✓ slack.py 코드, 자동 트리거 ✗ | **GAP** |
| §8.3 연속 2회 WARN | 격상 알림 | ✗ 미구현 | **GAP** |
| §9 9 엔드포인트 | /api/grant/* | ✓ 19 라우트 등록 | OK |
| §11 운영 비침습 | additive only | ✓ verify_schema.py 7/7 | OK |

---

## B. 갭 상세 (우선순위 순)

### G1 · BIZINFO `_extract_period` 정규식 약함 (HIGH)
**증상**: 스모크 결과 `2026.05.21 ~` 형태로 잘림 → start_date=None, end_date에 시작일이 들어감.
**원인**: `_PERIOD_LABEL_RE`가 일반 문자만 캡처해서 다음 셀(종료일)을 못 잡음. 라벨이 `<td>`/`<dd>`처럼 분리된 DOM에서 양쪽 날짜를 모두 잡으려면 셀 단위 파싱이 필요.
**위치**: [backend/src/total_support/scrapers/bizinfo.py:159](../../../backend/src/total_support/scrapers/bizinfo.py)
**위험**: D-Day 계산 부정확 → 마감 임박 하이라이트 누락.
**수정 방안**: 라벨 인접 2개 날짜를 동시에 잡는 정규식 + 셀 기반 fallback.

### G2 · LIVE 모드 detail 모달 API 호출 누락 (HIGH)
**증상**: 사용자가 공고 클릭 → 모달 열리는데 `content_html`이 null이라 빈 본문.
**원인**: `app.jsx:setDetail(p)`이 list item을 그대로 전달, LIVE 모드에서 `/postings/{id}/detail` 호출 분기 없음.
**위치**: [total_support_ui/app.jsx](../../../total_support_ui/app.jsx) setDetail 호출부
**수정 방안**: setDetail 시 LIVE면 `await API.getPostingDetail(p.id)`로 보강 후 setDetail.

### G3 · LIVE 모드 Bulk action API 호출 누락 (HIGH)
**증상**: `handleChangeReviewBulk`가 LIVE 모드 분기 없이 로컬 state만 변경 → 새로고침 시 사라짐.
**위치**: [total_support_ui/app.jsx](../../../total_support_ui/app.jsx) handleChangeReviewBulk
**수정 방안**: 각 id마다 PATCH 호출 (또는 백엔드 bulk endpoint 추가). 단순화: 병렬 PATCH.

### G4 · LIVE 모드 keyword preview API 호출 누락 (HIGH)
**증상**: KeywordEditModal의 "최근 100건 미리보기" 버튼이 mock의 postings에 대해 클라이언트에서 직접 매칭 — LIVE 모드에서 백엔드 키워드 변경 후 새로 추가될 데이터까지 정확히 시뮬레이션 안 됨.
**위치**: [total_support_ui/tabs-keywords.jsx](../../../total_support_ui/tabs-keywords.jsx) `runPreview()`
**수정 방안**: liveMode면 `API.previewKeyword({keyword, match_mode, ...})` 호출.

### G5 · iframe sandbox 이중 방어 (MEDIUM, PRD §6.3-③)
**증상**: 현재 `<div dangerouslySetInnerHTML>`로 렌더링. PRD는 "iframe sandbox로 격리해 스크립트 차단(저장 시 sanitize는 됐지만 이중 방어)" 명시.
**위치**: [total_support_ui/ui-kit.jsx:469](../../../total_support_ui/ui-kit.jsx)
**수정 방안**: srcdoc + sandbox="" 사용한 iframe으로 교체.

### G6 · 헬스 패널 백그라운드 폴링 (MEDIUM)
**증상**: LIVE 모드에서 trigger 후만 polling, 평소엔 정적 — 04:00 서버 자동 스케줄 결과를 프론트가 모름.
**위치**: [total_support_ui/app.jsx](../../../total_support_ui/app.jsx)
**수정 방안**: 30초마다 `API.getHealth()` 폴링 (선택적, 부하 가벼움).

### G7 · 자동 알림 cron 미가동 (MEDIUM)
**증상**: 36시간 stale 감지 코드(`health.is_stale`)와 Slack notify 함수는 있으나 **이를 자동 호출하는 Celery beat 잡 없음**.
**위치**: [backend/src/total_support/jobs/celery_app.py](../../../backend/src/total_support/jobs/celery_app.py)
**수정 방안**: `check_stale_and_alert` 태스크 + Beat 1시간 cron.

### G8 · 연속 2회 WARN 격상 미구현 (LOW)
**증상**: PRD §8.3 "같은 사이트가 연속 2회 WARN이면 알림". 현재 미구현.
**수정 방안**: G7과 같은 cron에서 최근 2회 run 조회 후 패턴 매칭.

### G9 · L2 API 통합 테스트 부재 (HIGH for QA)
**증상**: 56개 단위 테스트 통과했으나 FastAPI 라우터 TestClient 기반 통합 테스트 없음 — 라우팅/스키마 변경 시 회귀 감지 어려움.
**수정 방안**: pytest TestClient + in-memory(또는 docker postgres) 기반 테스트 추가.

### G10 · CORS 운영 환경 분리 (LOW)
**증상**: `allow_origins=["*"]` 모든 환경. 운영에선 화이트리스트 필요.
**위치**: [backend/src/total_support/api/main.py](../../../backend/src/total_support/api/main.py)
**수정 방안**: `Settings.cors_origins` 추가 → split.

---

## C. 우선순위 결정 (Act 단계 처리 대상)

**즉시 처리 (Act에서 수정)**:
- G1 BIZINFO 정규식 강화
- G2 LIVE detail 모달
- G3 LIVE bulk action
- G4 LIVE keyword preview
- G5 iframe sandbox
- G6 헬스 패널 폴링
- G7 stale/alert cron
- G9 L2 API 통합 테스트
- G10 CORS 환경변수화

**연기**:
- G8 연속 2회 WARN — G7 cron 안에서 같이 처리 (덤)

**라이브 검증 미실시 (배포 시점에 확인)**:
- IRIS 실 사이트 1페이지
- SBA 실 사이트 1페이지 (Playwright 브라우저 설치 + 실행 시간 필요)

---

## D. 측정 가능한 성공 기준

| 메트릭 | 현재 | 목표 (Act 후) |
|---|---|---|
| 테스트 수 | 56 단위 | 80+ (L1+L2) |
| BIZINFO start/end_date 추출률 | 1/5 (20%) | 4/5 이상 (80%) |
| LIVE 모드 풀 워크플로우 (수집→리뷰→상태변경) | 부분 | 완전 |
| iframe sandbox 활성 | 0 | 1 (감사 가능) |
| 36h stale 자동 알림 | 0 | 1 (Beat 스케줄러에 등록) |
| CORS 환경별 설정 | 0 | 1 (TS_CORS_ORIGINS env) |
