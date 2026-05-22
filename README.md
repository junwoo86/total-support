# Total Support · 지원사업 통합 수집 및 다중 분야 스크리닝

정부/지자체 지원사업 공고를 **기업마당 · IRIS · SBA** 3대 사이트에서 자동 수집하고, 4대 분야(AI / 바이오 / 헬스케어 / 웰니스) 키워드로 자동 스크리닝하는 풀스택 시스템.

PRD v9.0 명세 기반 (모듈 경계 = `tb_grant_*` 5 테이블, 운영 DB 비침습 원칙 준수).

---

## 아키텍처

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          외부 (정부/지자체 사이트)                          │
│      ┌──────────────┐    ┌──────────────┐    ┌──────────────┐              │
│      │  기업마당     │    │    IRIS      │    │     SBA      │              │
│      │ (HTTP + HTML)│    │ (Form POST)  │    │ (Playwright) │              │
│      └──────┬───────┘    └──────┬───────┘    └──────┬───────┘              │
└─────────────┼──────────────────-┼───────────────────┼──────────────────────┘
              ▼                   ▼                   ▼
        ┌──────────────────────────────────────────────────────┐
        │  scrapers/{bizinfo,iris,sba}.py · base.py            │
        │   · Early Break: ZERO_NEW_PAGE / ALL_EXPIRED_2PAGES  │
        │   · parsers/period.py  6단계 P1~P6 접수기간 해석     │
        │   · parsers/sanitize.py  본문 XSS sanitize           │
        │   · screening/  4모드 매처 + negative_context        │
        └──────────────────────────┬───────────────────────────┘
                                   │ upsert
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │              PostgreSQL  (tb_grant_*)                │
        │  postings · domains · keywords · runs · system_logs  │
        │  ▸ additive-only 마이그레이션  ▸ Asia/Seoul 쿼리식    │
        └──────────────────────────┬───────────────────────────┘
                                   │  SQLAlchemy ORM
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │  services/  (비즈니스 로직 + 도메인 예외)             │
        │   NotFoundError → 404 · DuplicateError → 409 등       │
        └──────────────────────────┬───────────────────────────┘
                                   │
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │  api/  (FastAPI 라우터 — thin HTTP 어댑터)            │
        │   /api/grant/postings · /domains · /keywords         │
        │   /collection/{run,runs,health} · /logs              │
        └──────────────────────────┬───────────────────────────┘
                                   │  same-origin StaticFiles
                                   ▼
        ┌──────────────────────────────────────────────────────┐
        │  total_support_ui/  React 18 SPA (UMD + Babel)       │
        │   app.jsx (shell) + hooks.jsx (mutation/effect) +    │
        │   ui-kit / tabs-* / health-panel                     │
        └──────────────────────────────────────────────────────┘

        ┌────────────────────── 잡 큐 (옵션) ─────────────────────┐
        │  jobs/  Celery + Redis 가용 → tasks.py 우선             │
        │         Redis 부재 → inproc.py 스레드 fallback (dev)    │
        └─────────────────────────────────────────────────────────┘
```

레이어 경계 한 줄 정리:
- **scrapers** = 외부 사이트 → ORM upsert (네트워크 책임)
- **services** = 비즈니스 로직 + DB 접근 + 도메인 예외 raise
- **api/routers** = HTTP I/O 만 (request 검증 · response 모델 변환)
- **db** = ORM 모델 + StrEnum 정의 + 시간대 헬퍼

---

## API 명세 (OpenAPI)

백엔드를 띄우면 표준 OpenAPI 문서가 자동 생성됩니다.

| 리소스 | URL |
|---|---|
| **Swagger UI** | http://localhost:8000/api/grant/docs |
| OpenAPI 스키마 (JSON) | http://localhost:8000/api/grant/openapi.json |

### 주요 엔드포인트 (12개)

| Method | Path | 용도 |
|---|---|---|
| `GET`    | `/api/grant/ping` | 헬스 체크 |
| `GET`    | `/api/grant/postings` | 공고 목록 (필터·페이징·D-Day) |
| `GET`    | `/api/grant/postings/{id}/detail` | 공고 상세 (content_html 포함) |
| `PATCH`  | `/api/grant/postings/{id}/review-status` | 검토상태 변경 |
| `GET`    | `/api/grant/domains` | 분야 목록 |
| `POST`   | `/api/grant/domains` | 분야 추가 |
| `PATCH`  | `/api/grant/domains/{id}` | 분야 수정 |
| `DELETE` | `/api/grant/domains/{id}?hard={bool}` | soft / hard 삭제 |
| `GET`    | `/api/grant/domains/{id}/keywords` | 분야의 키워드 |
| `POST`   | `/api/grant/domains/{id}/keywords` | 키워드 추가 |
| `PATCH`  | `/api/grant/domains/{id}/keywords/{kid}` | 키워드 수정 |
| `DELETE` | `/api/grant/domains/{id}/keywords/{kid}` | 키워드 삭제 |
| `POST`   | `/api/grant/keywords/preview` | 최근 100건 키워드 미리보기 |
| `POST`   | `/api/grant/collection/run` | 수집 잡 트리거 |
| `GET`    | `/api/grant/collection/runs` | 수집 이력 |
| `GET`    | `/api/grant/collection/health` | 3사이트 헬스 카드 |
| `GET`    | `/api/grant/logs` | 시스템 로그 |

전체 스키마/예시/응답 코드는 Swagger UI 에서 인터랙티브하게 확인 가능합니다.

---

## 구성

```
total_support/
├─ backend/                    # FastAPI + SQLAlchemy + Alembic + Celery(+ in-proc fallback) + Playwright
│  ├─ alembic/                 # 마이그레이션 (additive only)
│  ├─ src/total_support/
│  │  ├─ api/                  # /api/grant/* — HTTP thin adapter
│  │  ├─ services/             # 비즈니스 로직 + 도메인 예외
│  │  ├─ db/                   # ORM 모델 5종 + StrEnum + Asia/Seoul 헬퍼
│  │  ├─ parsers/              # parse_period 6단계 + sanitize_html
│  │  ├─ screening/            # 4모드 키워드 매처 + backfill
│  │  ├─ scrapers/             # bizinfo, iris, sba + base.py (Early Break)
│  │  ├─ jobs/                 # Celery + in-proc fallback
│  │  └─ observability/        # tb_grant_system_logs + Slack
│  ├─ tests/                   # pytest 172건 (단위 + L2 API + L3 통합)
│  └─ scripts/                 # check_db, smoke_bizinfo, reset_collection_data, run_stack
├─ total_support_ui/           # React 18 UMD + Babel Standalone SPA
│  ├─ index.html               # 단일 부트
│  ├─ api-client.js            # mock ↔ live 자동 스위치
│  ├─ app.jsx                  # 루트 shell (상태 선언 + 훅 조립 + 렌더)
│  ├─ hooks.jsx                # mutation/effect 훅 6개 (LIVE 부트스트랩,
│  │                           #   posting review, health polling, run
│  │                           #   trigger, running timer, domain/keyword CRUD)
│  ├─ ui-kit.jsx               # 디자인 시스템 컴포넌트
│  ├─ health-panel.jsx         # 헬스 카드 + 진행도 incremental
│  ├─ tabs-*.jsx               # 5탭 화면
│  └─ styles/                  # 디자인 시스템 v2 CSS
└─ docs/pdca/total_support/    # PDCA Plan→Do→Check→Act→QA 산출물
```

---

## 빠른 시작

```powershell
# 1. 백엔드
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. .env 작성
copy .env.example .env
# 편집 — TS_DATABASE_URL 등 채움

# 3. 마이그레이션 (additive only)
alembic upgrade head

# 4. (선택) Playwright Chromium 설치 (SBA 스크래퍼용)
python -m playwright install chromium

# 5. 백엔드 + SPA 동시 가동
.\scripts\run_stack.ps1
# → http://localhost:8000/ui/   (자동 LIVE 모드)
# → http://localhost:8000/api/grant/docs
```

대시보드는 별도 빌드 없이 단일 명령으로 동작 (React UMD + Babel Standalone).

---

## 핵심 기능

### 백엔드
- **3 사이트 스크래퍼** (httpx+selectolax / Form POST / Playwright)
- **6단계 접수기간 파서** P1~P6 (ISO date · 단편형 · 상시/예산 소진 · 공고일+N일 · 자유 자연어)
- **4모드 키워드 매처** WORD_BOUNDARY / EXACT_HANGUL / SUBSTRING / REGEX + `negative_context` 좌우 30자 윈도우
- **Early Break 2단계**: `ZERO_NEW_PAGE` + `ALL_EXPIRED_2PAGES` (방대 초기 수집에서 무의미한 깊은 페이지 차단)
- **Celery + Redis** 잡 큐, Redis 없으면 **in-process threading fallback** (단일팀 dev 환경 친화)
- **HTML sanitize** + 본문 iframe sandbox 격리 (XSS 2중 방어)
- **운영 DB 비침습**: `ALTER SYSTEM/DATABASE/ROLE` 일절 없음, `AT TIME ZONE 'Asia/Seoul'` 쿼리식만 사용
- **172 테스트 통과** (단위 + 라우터 통합 + 서비스 직접 + Enum drift 가드)

### 프론트엔드
- React 18 SPA (UMD + Babel Standalone — 빌드 단계 없음)
- 5탭: 신규 미검토 / 상태별 모니터링 / 헬스 모니터 / 분야·키워드 관리 / 시스템 로그
- **30개씩 페이징** + 적합도/출처/분야/검색 필터 조합
- 헬스 카드 RUNNING 진행도 실시간 (5초 폴링)
- 일괄 선택 + Bulk PATCH
- LIVE 모드 자동 진입 (백엔드와 같은 origin) — `?live=1` / `?mock=1` 강제 가능

---

## PDCA 산출물

| Phase | 문서 |
|---|---|
| Check (Analyze) | `docs/pdca/total_support/04-analysis.md` |
| Act (Iterate) | `docs/pdca/total_support/05-iteration.md` |
| QA L1~L5 | `docs/pdca/total_support/06-qa-report.md` |
| 아키텍처 | `backend/ARCHITECTURE.md` |
| DBA 인계 | `backend/DBA_HANDOFF.md` |

---

## 라이센스

Proprietary (사내 사용 목적).
