import os
from pathlib import Path
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SUPPORTIQ_",
        env_file=(str(_ROOT / ".env"), str(_ROOT / ".local/backend.env"), ".env", ".local/backend.env"),
        extra="ignore"
    )

    database_url_app: SecretStr
    database_url_owner: SecretStr | None = None
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:5173", "http://127.0.0.1:5173"])
    session_cookie_secure: bool = True
    session_idle_timeout_ms: int = 1_800_000
    session_absolute_lifetime_ms: int = 28_800_000
    sign_in_failure_limit: int = 5
    sign_in_failure_window_ms: int = 900_000
    sign_in_failure_delay_ms: int = 2_000
    ai_service_base_url: str | None = None
    require_privacy_ner: bool = True
    ai_service_analysis_timeout_ms: int = 3_000
    ai_service_draft_timeout_ms: int = 11_000
    job_lease_ms: int = 20_000
    job_poll_interval_ms: int = 500
    job_concurrency: int = Field(default=4, ge=1, le=16)
    backend_build: str = "application-v1"

    @model_validator(mode="after")
    def _enforce_strict_privacy_ner(self) -> "Settings":
        env_val = os.environ.get("SUPPORTIQ_REQUIRE_PRIVACY_NER")
        if env_val is not None and env_val.strip().lower() in {"0", "false", "no", "off"}:
            raise ValueError("SUPPORTIQ_REQUIRE_PRIVACY_NER cannot disable strict privacy NER")
        if self.ai_service_base_url is not None and not self.require_privacy_ner:
            raise ValueError("require_privacy_ner cannot be False when ai_service_base_url is configured")
        return self
