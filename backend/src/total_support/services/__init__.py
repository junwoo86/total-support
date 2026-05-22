"""Service layer — 비즈니스 로직과 DB 접근을 라우터로부터 분리.

PRD §11.4 (관심사 분리):
- routers/  : HTTP 입출력(요청 검증/응답 모델 변환) 만 담당.
- services/ : DB 조회·변경, 도메인 규칙, 부수효과(system_logs 적재 등).
- db/       : SQLAlchemy ORM 모델 + 엔진/세션.

서비스는 framework 비의존 예외(`ServiceError` 하위)만 raise. FastAPI 의
`exception_handler` (api/main.py) 가 이를 HTTP status code 로 변환한다.
"""

from total_support.services import domains, keywords, logs, postings
from total_support.services.exceptions import (
    DuplicateError,
    InvalidPatternError,
    NotFoundError,
    ServiceError,
)

__all__ = [
    "domains",
    "keywords",
    "logs",
    "postings",
    "ServiceError",
    "NotFoundError",
    "DuplicateError",
    "InvalidPatternError",
]
