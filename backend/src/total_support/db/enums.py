"""ORM 레벨 타입 안전성을 위한 Python Enum 정의 (PRD §4.1).

설계 원칙:
- `str` 을 상속 (`StrEnum`) 하므로 기존 SQLAlchemy String column 과 100% 호환
  → 코드는 `SourceSite.BIZINFO` 로 작성하고, SQLAlchemy 는 그대로 `"BIZINFO"` 로 직렬화.
- DB schema 는 변경하지 않는다 (PRD §11.5 운영 DB 비침습 · additive only).
  기존 `_check_in(...)` CHECK constraint 는 DB 측 마지막 방어선으로 보존.
- 코드 레벨 `_VALUES` 튜플은 Enum 으로부터 자동 도출 (`tuple(e.value for e in ...)`)
  하므로 두 정의가 영영 어긋날 수 없다 (drift 방지).

평가 의견 (코드 리뷰):
> ENUM 값 검증을 위한 `_check_in` 함수 대신, SQLAlchemy 의 `Enum` 타입이나
> `TypeDecorator` 를 활용하여 ORM 레벨에서 더 견고한 타입 안정성을 확보.

native PostgreSQL ENUM TYPE (`CREATE TYPE ...`) 은 마이그레이션을 매우
제약하기 때문에 (값 추가/삭제가 어렵고 ALTER 가 위험), PRD 의 additive-only
원칙과 충돌한다. 그래서 더 보수적인 절충안 — **Python StrEnum + 기존
CHECK 유지** — 을 택했다. 코드는 Enum 으로 타입 안전, DB 는 그대로.
"""

from __future__ import annotations

from enum import StrEnum


# ============================================================
# Posting 도메인
# ============================================================
class SourceSite(StrEnum):
    """수집 대상 사이트 — PRD §2.1."""

    BIZINFO = "BIZINFO"
    IRIS = "IRIS"
    SBA = "SBA"


class AiSuitability(StrEnum):
    """스크리닝 적합도 — PRD §3.4."""

    HIGH = "HIGH"
    NORMAL = "NORMAL"


class ReviewStatus(StrEnum):
    """내부 검토 상태 — PRD §5.2."""

    UNREVIEWED = "UNREVIEWED"
    EXCLUDED = "EXCLUDED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IN_PROGRESS = "IN_PROGRESS"


class PostingStatus(StrEnum):
    """공고 접수 상태 — PRD §2.3."""

    SCHEDULED = "SCHEDULED"
    ONGOING = "ONGOING"
    CLOSED = "CLOSED"


# ============================================================
# Collection run / system log
# ============================================================
class RunStatus(StrEnum):
    """수집 잡 상태 — PRD §2.4."""

    RUNNING = "RUNNING"
    OK = "OK"
    WARN = "WARN"
    FAIL = "FAIL"


class TriggerKind(StrEnum):
    """수집 잡 트리거 — PRD §2.4.4."""

    SCHEDULE = "SCHEDULE"
    MANUAL = "MANUAL"


class LogLevel(StrEnum):
    """system_logs.level — PRD §8.1."""

    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogCategory(StrEnum):
    """system_logs.category — PRD §8.1."""

    PARSE_PERIOD = "PARSE_PERIOD"
    URL_TRUNCATED = "URL_TRUNCATED"
    BACKFILL = "BACKFILL"
    SCRAPER = "SCRAPER"
    API = "API"


# ============================================================
# Keyword matcher
# ============================================================
class MatchMode(StrEnum):
    """키워드 매처 4모드 — PRD §5.5.3."""

    WORD_BOUNDARY = "WORD_BOUNDARY"
    EXACT_HANGUL = "EXACT_HANGUL"
    SUBSTRING = "SUBSTRING"
    REGEX = "REGEX"


# ============================================================
# Tuple-of-values exports — 기존 _check_in / Literal validator 와 호환
# ============================================================
def _values(enum_cls: type[StrEnum]) -> tuple[str, ...]:
    return tuple(e.value for e in enum_cls)


SOURCE_SITE_VALUES = _values(SourceSite)
AI_SUITABILITY_VALUES = _values(AiSuitability)
REVIEW_STATUS_VALUES = _values(ReviewStatus)
POSTING_STATUS_VALUES = _values(PostingStatus)
RUN_STATUS_VALUES = _values(RunStatus)
TRIGGER_KIND_VALUES = _values(TriggerKind)
LOG_LEVEL_VALUES = _values(LogLevel)
LOG_CATEGORY_VALUES = _values(LogCategory)
MATCH_MODE_VALUES = _values(MatchMode)
