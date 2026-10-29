from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    app_db_url: str = Field(default="sqlite+aiosqlite:///:memory:", alias="APP_DB_URL")
    audit_writer_db_url: str = Field(default="sqlite+aiosqlite:///:memory:", alias="AUDIT_WRITER_DB_URL")
    audit_reader_db_url: str = Field(default="sqlite+aiosqlite:///:memory:", alias="AUDIT_READER_DB_URL")
    vault_db_url: str = Field(default="sqlite+aiosqlite:///:memory:", alias="VAULT_DB_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    app_encryption_key: str = Field(
        default="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        alias="APP_ENCRYPTION_KEY"
    )
    internal_service_token: str = Field(default="test-internal-service-token", alias="INTERNAL_SERVICE_TOKEN")
    jwt_secret_key: str = Field(default="test-jwt-secret-key-at-least-32-chars-long", alias="JWT_SECRET_KEY")
    ml_inference_url: str = Field(default="http://localhost:8001", alias="ML_INFERENCE_URL")
    egress_proxy_url: str | None = Field(default=None, alias="EGRESS_PROXY_URL")
    llm_api_url: str = Field(default="https://api.openai.com/v1/chat/completions", alias="LLM_API_URL")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
