"""환경변수 로더.

`.env` 파일을 읽어 Pydantic Settings로 노출한다.
모든 환경변수는 `TS_` 접두사를 가져 다른 모듈과 충돌하지 않는다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 디렉토리 = 이 파일 기준 ../../..
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """런타임 설정. `.env`와 환경변수에서 자동 로드."""

    model_config = SettingsConfigDict(
        env_file=_BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        env_prefix="TS_",
        extra="ignore",
    )

    # --- DB --------------------------------------------------
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "biocom"
    db_user: str = "postgres"
    db_password: str = ""
    database_url: str = Field(
        default="",
        description="완전한 SQLAlchemy DSN. 비어있으면 위 부분에서 조합한다.",
    )
    db_statement_timeout_ms: int = 30_000

    # --- Redis -----------------------------------------------
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- 옵션 ------------------------------------------------
    slack_webhook_url: str = ""

    # --- CORS (G10) ------------------------------------------
    # 콤마 구분. development는 "*" 허용. 운영은 화이트리스트.
    cors_origins: str = "*"

    # --- 운영 ------------------------------------------------
    env: str = "development"
    log_level: str = "INFO"
    tz: str = "Asia/Seoul"

    # --- Vertex AI Gemini (C 제안: 본문 요약) ------------------
    # 인증은 ADC. 로컬: `gcloud auth application-default login`,
    # Cloud Run: 서비스 계정 바인딩. 코드에 키 노출 없음.
    # gcp_project_id 가 빈 문자열이면 summarizer 비활성 (= 기존 동작 유지).
    #
    # Biocom-lab 최신 패턴(2026-05) 차용:
    #   GCP_REGION 은 다른 GCP 서비스(GCS, Cloud Run 등) 용으로 남기고,
    #   Gemini 는 별도 GEMINI_LOCATION 으로 분리한다 (기본값 "global" —
    #   Gemini global endpoint 사용 시 지역 제약·할당량 분리에 유리).
    gcp_project_id: str = ""
    gcp_region: str = "asia-northeast3"
    gemini_location: str = "global"
    gemini_model: str = "gemini-3.5-flash"
    gemini_timeout_s: float = 30.0
    gemini_max_input_chars: int = 8000  # token cost 보호 + 본문 컷오프

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def effective_database_url(self) -> str:
        """DSN이 명시되어 있으면 그대로, 없으면 부분에서 조합."""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql+psycopg://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 단위 싱글톤. 테스트에서 override할 땐 `get_settings.cache_clear()`."""
    return Settings()
