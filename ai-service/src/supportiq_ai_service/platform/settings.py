"""The settings of ai-service: one typed class, validated at startup (ARCH-33 to ARCH-37, PY-43).

Only the composition root creates `Settings` and passes plain values on, so no other code
reads the environment. Every setting is listed with a comment in `ai-service/.env.example`.
"""

from typing import Annotated

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every setting of ai-service, read from environment variables of the same name."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="forbid", frozen=True)

    # The token that `backend` sends as `Authorization: Bearer <token>`, the same value as its
    # `ai_service_token` setting. Secret (SEC-10): it lives only in the secret settings of both
    # components and never appears in a log or an error body (SEC-09).
    service_token: Annotated[SecretStr, Field(min_length=1)]
