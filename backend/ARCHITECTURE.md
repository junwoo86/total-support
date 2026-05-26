# Total Support Backend · Architecture

PRD v9.0 (2026-05-22) 기준 백엔드 구현 가이드.

## 1. 모듈 경계 (PRD §11)

본 모듈은 운영 PostgreSQL 인스턴스를 다른 모듈과 공유한다.
**추가하는 객체는 다음이 전부:**

| 객체 | 이름 |
|---|---|
| 테이블 | `tb_grant_postings`, `tb_grant_domains`, `tb_grant_keywords`, `tb_grant_collection_runs`, `tb_grant_system_logs`, `tb_grant_company_guideline` |
| Alembic 버전 | `tb_grant_alembic_version` (다른 모듈의 `alembic_version`과 완전 분리) |
| 시퀀스 | `tb_grant_keyword_version_seq` |
| 함수 | `fn_tb_grant_bump_keyword_version()` |
| 트리거 | `trg_tb_grant_keywords_bump_version`, `trg_tb_grant_domains_bump_version` |

> `tb_grant_company_guideline` 은 append-only 패턴 — `version` autoincrement 로 히스토리 누적, "현재" = `ORDER BY version DESC LIMIT 1`. 별도 history 테이블 없음.

**절대 하지 않는 것** (§11.1·§11.2):
- `ALTER SYSTEM` / `ALTER DATABASE` / `ALTER ROLE`
- 다른 모듈 테이블에 대한 `ALTER` / `CREATE INDEX` / `DROP`
- 세션/롤 `SET TIME ZONE`
- `CREATE EXTENSION`
- 슈퍼유저 권한 요구

## 2. 디렉토리 구조

```
backend/
├─ alembic/
│  ├─ env.py              ← include_object 훅 + version_table 분리
│  └─ versions/
│     ├─ 001_grant_initial_schema.py        ← 5 테이블 초기 스키마
│     ├─ 002_grant_seed_domains_keywords.py ← 시드 4 도메인 / 18 키워드
│     ├─ 003_grant_relevance.py             ← +tb_grant_company_guideline
│     │                                       +relevance_score/reason/version
│     └─ 004_grant_evaluation_failed.py     ← +evaluation_failed bool
├─ src/total_support/
│  ├─ config.py           ← .env 로더 (DSN/REDIS/SLACK/GCP_PROJECT)
│  ├─ db/
│  │  ├─ engine.py        ← statement_timeout connection-level
│  │  ├─ tz.py            ← AT TIME ZONE 'Asia/Seoul' helper만 사용
│  │  └─ models.py        ← ORM 6 모델 + ENUM CHECK (GrantCompanyGuideline 포함)
│  ├─ parsers/
│  │  ├─ period.py        ← P1~P6 우선순위 매트릭스 (PRD §2.3)
│  │  └─ sanitize.py      ← <script>/<iframe>/onclick 제거
│  ├─ screening/
│  │  ├─ matcher.py       ← 4모드 + neg_context 좌우 30자
│  │  └─ backfill.py      ← screened_with_version < latest 배치
│  ├─ scrapers/
│  │  ├─ base.py          ← run 적재 + Early Break + BODY_SELECTORS 추출
│  │  │                     + 수집 시점 회사 적합도 평가 (evaluator 호출)
│  │  ├─ bizinfo.py       ← httpx + selectolax + cpage 순회
│  │  ├─ iris.py          ← Form POST + ancmIng/ancmPre + 자체 상세
│  │  └─ sba.py           ← Playwright + __doPostBack
│  ├─ services/           ← 비즈니스 로직 + 도메인 예외 raise
│  │  ├─ postings.py      ← 필터(다중·버킷)·페이징·D-Day·counts·상세 트림
│  │  ├─ domains.py       ← 분야 CRUD + soft/hard delete
│  │  ├─ keywords.py      ← 키워드 CRUD + 미리보기
│  │  ├─ logs.py          ← system_logs 조회
│  │  ├─ evaluator.py     ← Vertex AI Gemini (ADC · JSON · 3회 재시도 ·
│  │  │                     temperature=0 · thinking_budget=0)
│  │  ├─ guidelines.py    ← 회사 지침 append-only + UNREVIEWED 자동 백필
│  │  └─ exceptions.py    ← NotFoundError → 404, DuplicateError → 409 ...
│  ├─ api/
│  │  ├─ main.py          ← FastAPI app + /api/grant/* 라우터 + StaticFiles /ui/
│  │  ├─ schemas.py       ← Pydantic v2 요청/응답 DTO
│  │  ├─ postings.py · domains.py · keywords.py · collection.py · logs.py
│  │  ├─ guidelines.py    ← GET/PUT 지침 + history
│  │  └─ deps.py
│  ├─ jobs/
│  │  ├─ celery_app.py    ← Beat 04:00 KST staggered
│  │  └─ tasks.py         ← scrape_site + run_backfill + advisory_lock
│  └─ observability/
│     ├─ logger.py        ← tb_grant_system_logs writer
│     └─ slack.py         ← FAIL/stale 알림
└─ tests/                 ← 229 tests (단위 + L2 API + L3 통합 + evaluator mock
                             + counts/bucket/CSV 파서 단위)
                            라이브 DB 가드 92건은 TS_TEST_LIVE_DB=1 환경변수
                            없으면 skip — 운영 데이터 보호용 hard guard.
```

## 3. 데이터 프로세스 시퀀스 (PRD §7)

```
스케줄러(Celery Beat 04:00 KST) 또는 사용자 "▶ 지금 실행"
        ↓
POST /api/grant/collection/run {site}  →  Celery enqueue
        ↓
scrape_site Task:
  1. pg_try_advisory_lock(841, site_id)              ─ §11.7
  2. tb_grant_collection_runs INSERT status=RUNNING  ─ 헬스 패널 즉시 노출
  3. iter_listing_pages (사이트별)
       - BIZINFO: GET ?cpage=N&rows=15 → selectolax
       - IRIS   : POST + pageIndex + ancmPrg
       - SBA    : Playwright __doPostBack
  4. 페이지별 source_id 중 신규만 fetch_detail
       - 페이지 전체 신규 0건 → Early Break (PRD §2.2)
  5. 각 신규 건:
       a. sanitize_html(content)        ─ §4.2
       b. parse_period(raw_period)      ─ §2.3 P1~P6
       c. screen(text, keywords)        ─ §3.3 4모드 + neg_context
       d. upsert (source_site, source_id)
  6. tb_grant_collection_runs UPDATE status=OK/WARN/FAIL
  7. system_logs 1행 + (옵션) Slack webhook
  8. pg_advisory_unlock
```

## 4. 시간대 (PRD §2.3.2 · §11.2)

**모든 시간 비교는 `db/tz.py` 헬퍼만 사용한다.**

```python
from total_support.db import seoul_today_expr, dday_expr

# 한국 기준 오늘
stmt = select(GrantPosting).where(GrantPosting.end_date >= seoul_today_expr())

# D-Day 계산
dday = dday_expr(GrantPosting.end_date)  # → end_date - (now() AT TIME ZONE 'Asia/Seoul')::date
```

`SET TIME ZONE`은 절대 호출하지 않는다. 커넥션 풀이 다른 모듈과 공유되어도 누수 없음.

## 5. 키워드 버전 + 백필 (PRD §3.3.3 · §8.2 · §11.9)

- `tb_grant_keywords` / `tb_grant_domains` INSERT/UPDATE/DELETE 트리거가
  `tb_grant_keyword_version_seq` `nextval()` 호출.
- API에서 키워드 변경 후 백엔드가 `run_backfill` Celery 태스크 enqueue (선택).
- 백필 잡은 `screened_with_version < latest_version`인 posting을
  1,000행 배치(평일 09–18 KST는 5,000행 + 1초 sleep)로 재스캔.
- advisory lock `(841, 100)`로 동시 1개만 실행.

## 6. API 인터페이스 (PRD §9)

OpenAPI 자동 문서: `GET /api/grant/docs`.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/postings` | 서버 페이지네이션 + 다중 필터 + D-Day. `status`/`suitability`/`site`/`domain`/`relevance_bucket` 모두 CSV 다중값 (`status=NEEDS_REVIEW,IN_PROGRESS`). `relevance_bucket` 값: `high|mid_high|mid|low` (4단계 적합도 구간) |
| GET | `/postings/counts` | 검토 상태별 카운트 — `{UNREVIEWED, NEEDS_REVIEW, IN_PROGRESS, EXCLUDED}` 단일 GROUP BY |
| GET | `/postings/{id}/detail` | content_html 포함 (사이트별 selector 로 본문 트림) |
| PATCH | `/postings/{id}/review-status` | 상태 변경 + system_logs 적재 |
| GET / POST / PATCH / DELETE | `/domains` | 분야 CRUD (soft delete default) |
| GET / POST / PATCH / DELETE | `/domains/{id}/keywords` | 키워드 CRUD |
| POST | `/keywords/preview` | 100건 매칭 시뮬레이션 |
| GET / PUT | `/company-guideline` | 회사 적합도 평가용 시스템 지침. PUT 시 `reevaluate=false` 면 백필 트리거 X |
| GET | `/company-guideline/history` | 지침 버전 히스토리 (append-only) |
| POST | `/collection/run` | 수동 트리거 |
| GET | `/collection/runs` | 30일 이력 |
| GET | `/collection/health` | 헬스 카드 3개 (36h stale 감지) |
| GET | `/logs` | 시스템 로그 (필터) |

## 7. 빠른 시작

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 1. .env 작성 (DB DSN, REDIS, SLACK_WEBHOOK, GCP_PROJECT_ID 선택)
copy .env.example .env  # 후 직접 편집

# 2. 마이그레이션 (additive only)
alembic upgrade head

# 3. DB 연결 + 스키마 검증
python scripts/check_db.py
python scripts/verify_schema.py

# 4. (선택) Vertex AI Gemini 적합도 평가 활성화
#    TS_GCP_PROJECT_ID 비어있으면 평가는 자동 비활성 — 다른 기능 정상.
gcloud auth application-default login
gcloud auth application-default set-quota-project $env:TS_GCP_PROJECT_ID

# 5. (선택) Playwright Chromium (SBA 스크래퍼용)
python -m playwright install chromium

# 6. 풀스택 단일 실행 (API + StaticFiles SPA 동시)
.\scripts\run_stack.ps1
# → http://localhost:8000/ui/        (자동 LIVE 모드)
# → http://localhost:8000/api/grant/docs

# 또는 직접 uvicorn (개발 시 --reload 권장)
python -m uvicorn total_support.api.main:app --port 8000 --reload --reload-dir src

# 7. Celery 워커 (별도 셸; Redis 필요)
celery -A total_support.jobs.celery_app:celery_app worker -l info

# 8. Celery Beat (별도 셸)
celery -A total_support.jobs.celery_app:celery_app beat -l info
```

## 8. 프론트엔드 연결

API 서버가 `/ui/` 경로에 SPA 정적 파일을 마운트 — 동일 origin 자동 LIVE 모드.

| 접속 방법 | 모드 | 비고 |
|---|---|---|
| `http://localhost:8000/ui/` | LIVE (자동) | 동일 origin 감지 |
| `http://localhost:8000/ui/?live=1` | LIVE 강제 | |
| `http://localhost:8000/ui/?mock=1` | MOCK 강제 | 백엔드 무관 디자인 확인 |
| `?api=http://other:9000` | LIVE | base URL override |
| `total_support_ui/index.html` (file://) | MOCK | 백엔드 없이 시드 데이터 |

## 9. 테스트

```powershell
# 기본 (라이브 DB 가드된 92건은 skip — 운영 데이터 보호)
pytest tests/ -v

# 라이브 DB 통합 테스트까지 실행 (정책 데이터 변경 가능)
$env:TS_TEST_LIVE_DB=1; pytest tests/ -v
```

현재 **229 테스트 collected** — 기본 137 통과 + 92 라이브 가드 skip.

## 10. PRD §10 체크리스트 매핑

| PRD 항목 | 구현 위치 |
|---|---|
| Alembic 마이그레이션 (additive only) | [alembic/versions/](alembic/versions/) — 001~004 |
| 시드 데이터 (분야 4 + 키워드 18) | [002_grant_seed_*](alembic/versions/002_grant_seed_domains_keywords.py) |
| 회사 적합도 평가 (Vertex AI Gemini) | [services/evaluator.py](src/total_support/services/evaluator.py) + [003_grant_relevance.py](alembic/versions/003_grant_relevance.py) |
| 회사 지침 append-only + 자동 백필 | [services/guidelines.py](src/total_support/services/guidelines.py) |
| 스크래퍼 3종 + 단위 테스트 | [src/total_support/scrapers/](src/total_support/scrapers/) + tests/test_*_parsing.py |
| `parse_period` 12 케이스 | [tests/test_period.py](tests/test_period.py) |
| `screen` 4모드 + neg_context | [tests/test_screening.py](tests/test_screening.py) |
| 서버 페이지네이션 + 다중 필터 + 적합도 버킷 | [services/postings.py](src/total_support/services/postings.py) + [tests/test_posting_filters.py](tests/test_posting_filters.py) |
| Celery + `POST /api/grant/collection/run` | [src/total_support/jobs/](src/total_support/jobs/) + [api/collection.py](src/total_support/api/collection.py) |
| 대시보드 SPA (5탭 + 헬스 + 백오피스) | `total_support_ui/` (StaticFiles `/ui/` 마운트 — 동일 origin 자동 LIVE) |
| Slack 옵션 통합 | [observability/slack.py](src/total_support/observability/slack.py) |
| 스테이징 04:00 1주 관찰 | Beat 스케줄 활성화 후 [collection_runs](src/total_support/api/collection.py) 모니터링 |
| 라이브 DB 쓰기 가드 (테스트) | [tests/conftest.py](tests/conftest.py) — `LIVE_DB_GUARD_ENABLED` |
