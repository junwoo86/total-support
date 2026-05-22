"""Service-layer 도메인 예외.

서비스는 FastAPI 에 의존하지 않으므로 HTTPException 을 직접 raise 하지
않는다. 대신 의미가 명확한 도메인 예외를 던지고, api/main.py 의
exception_handler 가 HTTP status code 로 변환한다.

매핑:
- NotFoundError       → 404
- DuplicateError      → 409
- InvalidPatternError → 422
"""

from __future__ import annotations


class ServiceError(Exception):
    """모든 서비스 예외의 베이스."""


class NotFoundError(ServiceError):
    """리소스를 찾을 수 없음."""


class DuplicateError(ServiceError):
    """유니크 제약 위반(중복 키 등)."""


class InvalidPatternError(ServiceError):
    """사용자 입력이 도메인 규칙 위반(잘못된 정규식 등).

    Pydantic schema 단계에서 잡히지 않는 의미적 검증 실패에 사용.
    """
