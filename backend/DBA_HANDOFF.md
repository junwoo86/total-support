# DBA / 인프라 팀 인계 문서

**모듈명**: `total_support` (지원사업 통합 수집 및 다중 분야 스크리닝)
**PRD 버전**: v9.0 (Engineering-Ready, 2026-05-22)
**대상 인스턴스**: PostgreSQL 17.9 (GCP Cloud SQL, `34.47.95.104:5432/dashboard-dev`)

---

## 한 줄 요약 (PRD §11.12)

> 본 모듈은 같은 PostgreSQL 인스턴스 안에 `tb_grant_*` 6개 테이블, `tb_grant_alembic_version` 1개 마이그레이션 추적 테이블, `tb_grant_keyword_version_seq` 1개 시퀀스만 추가 생성하며, 기존 DB·롤·시스템 파라미터·다른 모듈 테이블에는 어떤 ALTER도 수행하지 않습니다. 시간대는 쿼리식 `AT TIME ZONE 'Asia/Seoul'`로만 처리하며, 슈퍼유저 권한도 요구하지 않습니다.

---

## 1. 추가되는 객체 (전체)

### 테이블 (6)
| 테이블 | 행 추정 | 목적 |
|---|---|---|
| `tb_grant_postings` | 일 ~30~50건, 무기한 보존 | 메인 — 공고 본문 + 스크리닝 결과 + AI 적합도 점수/사유 |
| `tb_grant_domains` | 5~10 | 분야 마스터 (AI/바이오/헬스케어/웰니스) |
| `tb_grant_keywords` | ~50 | 분야별 매칭 키워드 |
| `tb_grant_collection_runs` | 일 ~9건 (3사이트 × 3시간대), 90일 보존 | 수집 실행 이력 |
| `tb_grant_system_logs` | 일 ~100~500건, level별 30/180/무기한 | 운영 이벤트 로그 |
| `tb_grant_company_guideline` | 지침 수정 시마다 1행 누적 (append-only) | 회사 적합도 평가용 시스템 지침 (Vertex AI Gemini 입력). "현재" = ORDER BY version DESC LIMIT 1 |

### 보조 객체
| 객체 | 용도 |
|---|---|
| `tb_grant_alembic_version` | 본 모듈 전용 마이그레이션 추적 (기존 `alembic_version` 무손상) |
| `tb_grant_keyword_version_seq` | 키워드 변경 감지 시퀀스 |
| `fn_tb_grant_bump_keyword_version()` | 시퀀스 증가 트리거 함수 |
| `trg_tb_grant_keywords_bump_version` | 키워드 INSERT/UPDATE/DELETE 트리거 |
| `trg_tb_grant_domains_bump_version` | 도메인 INSERT/UPDATE/DELETE 트리거 |

### 인덱스 (모두 본 모듈 테이블 위에만)
- `idx_tb_grant_postings_unique (source_site, source_id)` — UNIQUE
- `idx_tb_grant_postings_review_status`
- `idx_tb_grant_postings_end_date`
- `idx_tb_grant_postings_ai_suitability`
- `ix_tb_grant_keywords_domain_id`
- `idx_tb_grant_collection_runs_site_started`
- `idx_tb_grant_system_logs_created`
- `idx_tb_grant_system_logs_level_category`

---

## 2. 권한 요청 (최소 권한 원칙)

### 옵션 A · 전용 사용자 신설 (권장 · PRD §11.3)

```sql
CREATE USER tb_grant_app WITH PASSWORD '<생성한_비밀번호>';
GRANT CONNECT ON DATABASE "dashboard-dev" TO tb_grant_app;
GRANT USAGE ON SCHEMA public TO tb_grant_app;

-- 본 모듈 6 테이블 + alembic 추적 테이블만 RW
GRANT SELECT, INSERT, UPDATE, DELETE
  ON tb_grant_postings, tb_grant_domains, tb_grant_keywords,
     tb_grant_collection_runs, tb_grant_system_logs, tb_grant_company_guideline,
     tb_grant_alembic_version
  TO tb_grant_app;

GRANT USAGE ON SEQUENCE tb_grant_keyword_version_seq TO tb_grant_app;

-- Alembic이 신규 테이블의 시퀀스도 사용
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tb_grant_app;
```

### 옵션 B · 기존 앱 사용자에 권한만 추가
위 GRANT 절만 적용 (다른 권한은 변경 없음).

### 현재 운영 상태 (참고)
운영자 요청에 따라 임시로 `postges` 슈퍼유저로 접속 중. 운영 전환 시 옵션 A로 분리 권장.

---

## 3. 배포 절차

```bash
cd backend
alembic upgrade head      # 약 0.8초 소요 (6 테이블 + 1 시퀀스 + 2 트리거 + 시드 22 INSERT
                          #   + 003 평가 컬럼 + 004 evaluation_failed 컬럼)
python scripts/verify_schema.py  # 자동 검증
```

업무 외 시간 적용 권장. 마이그레이션 자체는 신규 테이블 생성이므로 락 영향 없음.

---

## 4. 운영 안전 가드 (PRD §11.11)

배포 후 7일간 다음 지표 관찰:

| 지표 | 임계치 | 측정 방법 |
|---|---|---|
| 전체 DB 평균 쿼리 응답시간 | ±5% 이내 | `pg_stat_statements` 또는 외부 APM |
| 본 모듈 사용자 idle-in-transaction | 0건 | `SELECT * FROM pg_stat_activity WHERE state='idle in transaction' AND usename='tb_grant_app'` |
| 본 모듈 테이블 락 대기 시간 | 즉시 해소 | `pg_locks` |
| 04:00 배치 시 다른 모듈 응답시간 회귀 | ±5% 이내 | 동일 |

임계치 초과 시:
1. Celery Beat 비활성화 (`celery beat` 프로세스 종료)
2. 본 모듈 사용자 세션 종료 (`SELECT pg_terminate_backend(pid) ... WHERE usename='tb_grant_app'`)
3. 필요 시 `alembic downgrade base` (본 모듈 객체만 정확히 제거됨, 외부 영향 0)

---

## 5. 데이터 보존 정책 (PRD §8.4)

| 테이블 | 보존 |
|---|---|
| `tb_grant_postings` | 무기한 |
| `tb_grant_collection_runs` | 90일 후 월 1회 파티션 드롭 (수동 또는 별도 cron) |
| `tb_grant_system_logs` | INFO 30일 / WARN 180일 / ERROR 무기한 |
| `tb_grant_company_guideline` | 무기한 (append-only — 지침 버전 히스토리) |

삭제는 모두 본 모듈 테이블 내부에서만 수행 — 외부 영향 0.

---

## 6. 응급 연락처 / 롤백 명령

```bash
# 즉시 비활성화
celery -A total_support.jobs.celery_app:celery_app control shutdown

# 본 모듈 사용자 세션 강제 종료
psql -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE usename='tb_grant_app'"

# 전체 down (5 테이블 + 시퀀스 + 트리거만 제거, 외부 무영향)
alembic downgrade base
```
