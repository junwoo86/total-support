# Total Support Backend · Architecture

PRD v9.0 (2026-05-22) 기준 백엔드 구현 가이드.

## 1. 모듈 경계 (PRD §11)

본 모듈은 운영 PostgreSQL 인스턴스를 다른 모듈과 공유한다.
**추가하는 객체는 다음이 전부:**

| 객체 | 이름 |
|---|---|
| 테이블 | `tb_grant_postings`, `tb_grant_domains`, `tb_grant_keywords`, `tb_grant_collection_runs`, `tb_grant_system_logs` |
| Alembic 버전 | `tb_grant_alembic_version` (다른 모듈의 `alembic_version`과 완전 분리) |
| 시퀀스 | `tb_grant_keyword_version_seq` |
| 함수 | `fn_tb_grant_bump_keyword_version()` |
| 트리거 | `trg_tb_grant_keywords_bump_version`, `trg_tb_grant_domains_bump_version` |

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
│     ├─ 001_grant_initial_schema.py
│     └─ 002_grant_seed_domains_keywords.py
├─ src/total_support/
│  ├─ config.py           ← .env 로더
│  ├─ db/
│  │  ├─ engine.py        ← statement_timeout connection-level
│  │  ├─ tz.py            ← AT TIME ZONE 'Asia/Seoul' helper만 사용
│  │  └─ models.py        ← ORM 5 모델 + ENUM CHECK
│  ├─ parsers/
│  │  ├─ period.py        ← P1~P6 우선순위 매트릭스 (PRD §2.3)
│  │  └─ sanitize.py      ← <script>/<iframe>/onclick 제거
│  ├─ screening/
│  │  ├─ matcher.py       ← 4모드 + neg_context 좌우 30자
│  │  └─ backfill.py      ← screened_with_version < latest 배치
│  ├─ scrapers/
│  │  ├─ base.py          ← run 적재 + Early Break + upsert
│  │  ├─ bizinfo.py       ← httpx + selectolax + cpage 순회
│  │  ├─ iris.py          ← Form POST + ancmIng/ancmPre + 자체 상세
│  │  └─ sba.py           ← Playwright + __doPostBack
│  ├─ api/
│  │  ├─ main.py          ← FastAPI app + /api/grant/* 라우터
│  │  ├─ schemas.py       ← Pydantic v2 요청/응답 DTO
│  │  ├─ postings.py · domains.py · keywords.py · collection.py · logs.py
│  │  └─ deps.py
│  ├─ jobs/
│  │  ├─ celery_app.py    ← Beat 04:00 KST staggered
│  │  └─ tasks.py         ← scrape_site + run_backfill + advisory_lock
│  └─ observability/
│     ├─ logger.py        ← tb_grant_system_logs writer
│     └─ slack.py         ← FAIL/stale 알림
└─ tests/                 ← 56 tests (parse_period 12 + screen 19 + sanitize 10 + bizinfo 5 + iris 5 + sba 3 + 분석 등)
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

총 19개 라우트 (`/api/grant/*`). OpenAPI 자동 문서: `GET /api/grant/docs`.

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/postings` | 필터 + 페이징 + D-Day |
| GET | `/postings/{id}/detail` | content_html 포함 |
| PATCH | `/postings/{id}/review-status` | 상태 변경 |
| GET / POST / PATCH / DELETE | `/domains` | 분야 CRUD (soft delete default) |
| GET / POST / PATCH / DELETE | `/domains/{id}/keywords` | 키워드 CRUD |
| POST | `/keywords/preview` | 100건 매칭 시뮬레이션 |
| POST | `/collection/run` | 수동 트리거 |
| GET | `/collection/runs` | 30일 이력 |
| GET | `/collection/health` | 헬스 카드 3개 |
| GET | `/logs` | 시스템 로그 (필터) |

## 7. 빠른 시작

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 1. .env 작성 (DB DSN, REDIS, SLACK_WEBHOOK)
copy .env.example .env  # 후 직접 편집

# 2. 마이그레이션 (additive only)
alembic upgrade head

# 3. DB 연결 검증
python scripts/check_db.py
python scripts/verify_schema.py

# 4. BIZINFO 라이브 1페이지 스모크
python scripts/smoke_bizinfo.py

# 5. API 서버
python -m uvicorn total_support.api.main:app --port 8000

# 6. Celery 워커 (별도 셸; Redis 필요)
celery -A total_support.jobs.celery_app:celery_app worker -l info

# 7. Celery Beat (별도 셸)
celery -A total_support.jobs.celery_app:celery_app beat -l info
```

## 8. 프론트엔드 연결 (Phase 9)

`total_support_ui/index.html?live=1` 로 열면 백엔드(`http://localhost:8000`)
실 데이터를 표시. `?api=http://...`로 base URL override 가능.

- 기본 (`?live=` 없음): mockdata.js 시드 (디자인/UX 확인용)
- LIVE 모드: 모든 mutation이 실 API로 전송 + 폴링으로 헬스 갱신

## 9. 테스트

```powershell
pytest tests/ -v
```

현재 56개 테스트 통과 (네트워크 호출 없는 단위 테스트).

## 10. PRD §10 체크리스트 매핑

| PRD 항목 | 구현 위치 |
|---|---|
| Alembic 마이그레이션 (additive only) | [alembic/versions/](alembic/versions/) |
| 시드 데이터 (분야 4 + 키워드 18) | [002_grant_seed_*](alembic/versions/002_grant_seed_domains_keywords.py) |
| 스크래퍼 3종 + 단위 테스트 | [src/total_support/scrapers/](src/total_support/scrapers/) + tests/test_*_parsing.py |
| `parse_period` 12 케이스 | [tests/test_period.py](tests/test_period.py) |
| `screen` 4모드 + neg_context | [tests/test_screening.py](tests/test_screening.py) |
| Celery + `POST /api/grant/collection/run` | [src/total_support/jobs/](src/total_support/jobs/) + [api/collection.py](src/total_support/api/collection.py) |
| 대시보드 SPA (5탭 + 헬스 + 백오피스) | `total_support_ui/` (이미 구현됨, api-client.js 연결) |
| Slack 옵션 통합 | [observability/slack.py](src/total_support/observability/slack.py) |
| 스테이징 04:00 1주 관찰 | Beat 스케줄 활성화 후 [collection_runs](src/total_support/api/collection.py) 모니터링 |
