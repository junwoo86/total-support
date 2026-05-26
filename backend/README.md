# Total Support Backend

지원사업 통합 수집 및 다중 분야 스크리닝 백엔드 — **PRD v9.0** 구현.

## 모듈 경계 (중요)

본 모듈은 운영 PostgreSQL 인스턴스를 다른 모듈(`tb_sales_*`, `tb_restock_*` 등)과 공유합니다.
운영 DB 비침습 원칙(PRD §11)을 강제합니다:

- 추가하는 DDL은 **`tb_grant_*` 6 테이블 + `tb_grant_keyword_version_seq` 1 시퀀스 + 자기 테이블 트리거**가 전부
  (postings · domains · keywords · collection_runs · system_logs · **company_guideline**)
- `ALTER SYSTEM/DATABASE/ROLE` 절대 금지
- 시간대 처리는 쿼리식 `AT TIME ZONE 'Asia/Seoul'`로만 (세션 TZ 변경 금지) — `db/tz.py` 헬퍼만 사용
- 테스트 라이브 DB 쓰기 가드 — `TS_TEST_LIVE_DB=1` 환경변수가 없으면 운영 DB 변경 가능한 92건의 테스트는 자동 skip ([tests/conftest.py](tests/conftest.py))

## 디렉토리

```
backend/
├─ alembic/                  # 마이그레이션 (additive only) — 001~004
├─ src/total_support/
│  ├─ config.py              # .env 로더 (DSN, REDIS, SLACK_WEBHOOK, GCP_PROJECT_ID)
│  ├─ db/
│  │  ├─ engine.py           # SQLAlchemy engine/session
│  │  ├─ tz.py               # AT TIME ZONE 'Asia/Seoul' 헬퍼
│  │  └─ models.py           # ORM 6 모델 (postings · domains · keywords ·
│  │                         #              collection_runs · system_logs · company_guideline)
│  ├─ parsers/               # parse_period, sanitize_html
│  ├─ screening/             # 4모드 키워드 매처 + backfill
│  ├─ scrapers/              # bizinfo/iris/sba — BODY_SELECTORS 본문 추출 +
│  │                         #   수집 시점 회사 적합도 평가 (evaluator 연동)
│  ├─ services/              # 비즈니스 로직 + 도메인 예외
│  │                         #   postings (다중 필터·버킷·counts) /
│  │                         #   domains / keywords / logs /
│  │                         #   evaluator (Vertex AI Gemini ADC) /
│  │                         #   guidelines (회사 지침 append-only + 자동 백필)
│  ├─ api/                   # FastAPI thin adapter (/api/grant/* + StaticFiles /ui/)
│  ├─ jobs/                  # Celery tasks + Beat
│  └─ observability/         # tb_grant_system_logs writer + Slack
└─ tests/                    # 229 collected (137 단위 + 92 라이브 DB 가드)
```

## 빠른 시작

```powershell
# 1. 가상환경 + 의존성
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. .env 작성 (.env.example 참고)
copy .env.example .env

# 3. 마이그레이션 (additive only)
alembic upgrade head

# 4. (선택) 실 데이터 시드 — BIZINFO 3페이지 ~45건
python scripts/seed_more_postings.py

# 5. 풀스택 단일 실행 (API + SPA 동시)
.\scripts\run_stack.ps1

# 접속
#   - SPA   : http://localhost:8000/ui/    (자동 LIVE 모드)
#   - API   : http://localhost:8000/api/grant/...
#   - Docs  : http://localhost:8000/api/grant/docs
```

### 프론트엔드 모드

| 접속 방법 | 모드 |
|---|---|
| `http://localhost:8000/ui/` | LIVE (자동) — 동일 origin 감지 |
| `http://localhost:8000/ui/?live=1` | LIVE 강제 |
| `http://localhost:8000/ui/?mock=1` | MOCK 강제 (백엔드 무관하게 시드) |
| `total_support_ui/index.html` 직접 (file://) | MOCK (디자인 확인용) |

## PRD 매핑

| PRD 섹션 | 구현 위치 |
|---|---|
| §2.1 사이트별 스크래퍼 | `scrapers/{bizinfo,iris,sba}.py` + `scrapers/base.py` BODY_SELECTORS |
| §2.3 접수기간 파서 | `parsers/period.py` |
| §2.4 collection_runs | `scrapers/base.py` + `db/models.py` |
| §3.3 키워드 매처 | `screening/matcher.py` |
| §4 DB 스키마 | `alembic/versions/001_*` + `003_grant_relevance.py` + `004_grant_evaluation_failed.py` + `db/models.py` |
| §5.5 키워드 백오피스 API | `api/{domains,keywords}.py` |
| 회사 적합도 평가 (Vertex AI Gemini) | `services/evaluator.py` + `services/guidelines.py` + `api/guidelines.py` |
| 서버 페이지네이션 + 다중 필터 + 적합도 버킷 | `services/postings.py` + `api/postings.py` |
| §7 데이터 프로세스 | `scrapers/base.py` + `jobs/tasks.py` |
| §8 운영/백필/로그 | `screening/backfill.py` + `observability/` |
| §9 API 인터페이스 | `api/` |
| §11 운영 안전성 | `db/engine.py` (statement_timeout, additive only) + `tests/conftest.py` 라이브 DB 가드 |
