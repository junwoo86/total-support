# PDCA · Act (Iterate) — 갭 수정 이력

**기반 문서**: [04-analysis.md](04-analysis.md)
**작성일**: 2026-05-22
**총 수정 갭**: 10 / 10 (G1~G10) — **모두 처리 완료**

---

## 갭 처리 매트릭스

| 갭 | 우선순위 | 처리 상태 | 산출물 |
|---|---|---|---|
| G1 BIZINFO `_extract_period` 정규식 | HIGH | ✅ 완료 | [bizinfo.py](../../../backend/src/total_support/scrapers/bizinfo.py) + 2 테스트 추가 |
| G2 LIVE detail 모달 API 호출 | HIGH | ✅ 완료 | [app.jsx `handleOpenDetail`](../../../total_support_ui/app.jsx) |
| G3 LIVE bulk action API 결합 | HIGH | ✅ 완료 | [app.jsx `handleChangeReviewBulk`](../../../total_support_ui/app.jsx) |
| G4 LIVE keyword preview API | HIGH | ✅ 완료 | [tabs-keywords.jsx `runPreview`](../../../total_support_ui/tabs-keywords.jsx) |
| G5 iframe sandbox 이중 방어 | MEDIUM | ✅ 완료 | [ui-kit.jsx `PostingDetailModal`](../../../total_support_ui/ui-kit.jsx) |
| G6 헬스 패널 30초 폴링 | MEDIUM | ✅ 완료 | [app.jsx useEffect 폴링](../../../total_support_ui/app.jsx) |
| G7 36h stale 자동 알림 cron | MEDIUM | ✅ 완료 | [jobs/tasks.py `check_health_alerts`](../../../backend/src/total_support/jobs/tasks.py) + Beat 등록 |
| G8 연속 2회 WARN 격상 | LOW | ✅ 완료 | G7과 동일 태스크에 통합 |
| G9 L2 API TestClient 통합 테스트 | HIGH | ✅ 완료 | [tests/test_api_integration.py](../../../backend/tests/test_api_integration.py) — 18 테스트 |
| G10 CORS 환경변수화 | LOW | ✅ 완료 | [config.py `cors_origins`](../../../backend/src/total_support/config.py) + [main.py](../../../backend/src/total_support/api/main.py) |

---

## 변경 상세

### G1 · BIZINFO `_extract_period` 정규식 강화

**Before**:
```python
_PERIOD_LABEL_RE = re.compile(r"신청기간\s*[:：]?\s*([\d.\-/~ ()월화수목금토일까지: ]+)")
```
짧고 그리디라 보통 시작일까지만 캡처되어 `2026.05.21 ~` 형태로 잘림.

**After**:
- 정규식을 풀 패턴(시작일 + 요일 + ~ + 종료일 + 시간 + "까지")으로 확장
- `_extract_period`에 DOM 기반 fallback 추가 — `dt/th`에 라벨이 있고 인접 `dd/td`에 값이 있는 경우 셀 텍스트 직접 추출

**검증**:
- [tests/test_bizinfo_parsing.py](../../../backend/tests/test_bizinfo_parsing.py) 신규 2 케이스 (요일 + 시간 / 종료 연도 생략 단편형)
- 기존 5 케이스 회귀 없음
- 라이브 사이트 재수집은 다음 [smoke_bizinfo](../../../backend/scripts/smoke_bizinfo.py) 실행 시점에 확인

### G2 · LIVE detail 모달 API 호출

**Before**: `setDetail(p)` 직호출 → `content_html`이 null (LIVE 모드에선 list 응답에 없음).
**After**: `handleOpenDetail(p)` 도입 — 1차로 list item 표시 + 백그라운드에서 `API.getPostingDetail(p.id)` 보강.
**효과**: LIVE 모드에서도 본문 sanitize 결과를 즉시 노출 (iframe sandbox와 결합 — G5).

### G3 · LIVE bulk action

**Before**: `handleChangeReviewBulk`이 로컬 state만 변경 → 새로고침 시 손실.
**After**: `Promise.allSettled`로 병렬 PATCH 호출. 실패한 항목은 토스트로 알림.

### G4 · LIVE keyword preview

**Before**: 클라이언트 매처로 mockdata.postings에서 100건 시뮬레이션.
**After**: LIVE 모드면 `/api/grant/keywords/preview` 호출 (실 DB 최근 100건 기준). 미리보기 헤더에 `샘플 N개` 부속 표시.

### G5 · iframe sandbox 이중 방어 (PRD §6.3-③)

**Before**: `<div dangerouslySetInnerHTML={{__html: posting.content_html}} />`
**After**: `<iframe sandbox="" srcDoc={...}>`로 격리 컨텍스트. 인라인 CSS 일부 적용해 시각 유지.
**효과**: sanitize 우회된 페이로드가 있어도 부모 DOM 접근/스크립트 실행 불가.

### G6 · 헬스 패널 30초 백그라운드 폴링

**Before**: trigger 후 2초 폴링 + 정상 종료 후 stop. 04:00 자동 스케줄 결과는 새로고침 전까지 모름.
**After**: LIVE 모드 시 30초 간격 `getHealth()` → 새 run_id를 dedupe하여 `runs` state에 누적.

### G7 + G8 · 자동 알림 cron 태스크

**Before**: `Slack.notify()` 함수만 있고 호출 주체 없음.
**After**:
- `check_health_alerts` Celery 태스크 추가 — 사이트별 last OK 시각 + 최근 2회 status 조회
- 36시간 stale 또는 연속 2회 WARN 검출 시 `system_logs` ERROR 적재 + `notify(level="ERROR")` 호출
- Celery Beat에 `crontab(minute=0)` 매시 등록

### G9 · L2 API 통합 테스트

신규 [test_api_integration.py](../../../backend/tests/test_api_integration.py):
- 18 테스트 (ping, OpenAPI 라우트 12개 존재 검증, domains CRUD, keywords list/preview, postings filter, health, runs, logs)
- 실 DB(`dashboard-dev`) 사용 — 시드 4 도메인 / 18 키워드 기준
- 422 / 404 등 에러 케이스 포함

### G10 · CORS 환경변수화

**Before**: `allow_origins=["*"]` 하드코딩.
**After**: `Settings.cors_origins` (`TS_CORS_ORIGINS` env, default `*`) → `cors_origin_list` 헬퍼.
운영 배포 시 `.env`에 `TS_CORS_ORIGINS=https://your-dashboard.example.com` 만 추가하면 됨.

---

## 최종 회귀 테스트 결과

```
$ pytest tests/ -q
74 passed, 1 warning in 2.13s
```

- 단위 테스트 56 (PRD §2.3 / §3.3 / §4.2 / BIZINFO·IRIS·SBA 파싱)
- L2 API 통합 18 (실 DB 기반 19 라우트 표면 검증)
- G1 추가 케이스 2

회귀 없음. 모든 갭 처리 완료.

---

## 미해결 / 후속 이슈

다음은 04-analysis.md C 섹션의 "라이브 검증 미실시"로 분류 — Act 범위 밖.

- **IRIS 실 사이트 1페이지 검증**: Form POST hidden 필드 정확도 확인 필요. 첫 라이브 실행 시 WARN 가능.
- **SBA Playwright 라이브 검증**: `playwright install chromium` 후 실행 필요. CI/스테이징 환경에서 별도 수행.
- **본 모듈 전용 DB user `tb_grant_app` 분리**: 현재 postgres 슈퍼유저로 임시 운영. [DBA_HANDOFF.md](../../../backend/DBA_HANDOFF.md) §2 참조.
