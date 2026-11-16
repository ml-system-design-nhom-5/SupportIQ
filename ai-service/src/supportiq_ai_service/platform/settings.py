"""The settings of ai-service: one typed class, validated at startup (ARCH-33 to ARCH-37, PY-43).

Only the composition root creates `Settings` and passes plain values on, so no other code
reads the environment. Every setting is listed with a comment in `ai-service/.env.example`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, LiteralString, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, SettingsConfigDict

# The budget of the whole LLM step, retries included, is at most 10 seconds (NFR-07, ERR-10).
_MAX_LLM_BUDGET_MS = 10_000
# One attempt and up to two retries (requirements, Interpretations, row 1).
_MAX_LLM_ATTEMPTS = 3
# The range of the temperature that the Gemini API accepts.
_MAX_TEMPERATURE = 2.0


class Settings(BaseSettings):
    """Every setting of ai-service, read from environment variables of the same name."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="forbid", frozen=True)

    # The token that `backend` sends as `Authorization: Bearer <token>`, the same value as its
    # `ai_service_token` setting. Secret (SEC-10): it lives only in the secret settings of both
    # components and never appears in a log or an error body (SEC-09).
    service_token: Annotated[SecretStr, Field(min_length=1)]

    # The release manifest that the replica serves; its assets are in the same folder. Required:
    # ai-service has no fallback model, so it checks the manifest and every file it names at
    # startup and stops when one is missing or does not match (DATA-56, ERR-17). On Modal, the
    # manifest and its assets are in the folder that `modal deploy` adds to the image
    # (ADR-0018, Deploy).
    release_manifest_path: Path

    # The Gemini API key, used for nothing else (SEC-08, SEC-13). Secret (SEC-10): on Modal it
    # is a Modal Secret (ADR-0018, Secrets), and it goes only in the header of an LLM call.
    gemini_api_key: Annotated[SecretStr, Field(min_length=1)]
    # The Gemini model that drafts, such as `gemini-3.5-flash-lite`, the model of `main`. The
    # choice of the provider and the model waits for its own ADR (ADR-0021, Python and
    # dependencies, statement 4).
    gemini_model: Annotated[str, Field(pattern=r"^gemini-[a-z0-9._-]+$")]
    # The prices of the tokens of `gemini_model`, in millionths of a US dollar for one million
    # tokens, from the price list of the provider. They have no default, because a price in code
    # would be a number that nobody checked. Every result reports its cost (contract `LlmUsage`).
    llm_input_price_micro_usd_per_million_tokens: Annotated[int, Field(ge=0)]
    llm_output_price_micro_usd_per_million_tokens: Annotated[int, Field(ge=0)]
    # The budget of the whole LLM step, retries and waits included (NFR-07, ERR-10).
    llm_budget_ms: Annotated[int, Field(ge=1, le=_MAX_LLM_BUDGET_MS)] = _MAX_LLM_BUDGET_MS
    # The timeout of one attempt, within the budget (ERR-09); the value of `main`.
    llm_attempt_timeout_ms: Annotated[int, Field(ge=1, le=_MAX_LLM_BUDGET_MS)] = 5_000
    # The attempts of one LLM step, the first one included (ERR-13); the value of `main`.
    llm_max_attempts: Annotated[int, Field(ge=1, le=_MAX_LLM_ATTEMPTS)] = 2
    # The backoff before the second attempt, doubled after, and its maximum (ERR-13); the
    # values of `main`. Each wait is a random part of it (full jitter).
    llm_backoff_base_ms: Annotated[int, Field(ge=1)] = 250
    llm_backoff_max_ms: Annotated[int, Field(ge=0)] = 2_000
    # The maximum number of output tokens of a draft; the value of `main`.
    llm_max_output_tokens: Annotated[int, Field(ge=1)] = 1_024
    # The temperature of a draft, which only Gemini 2.5 models take; the value of `main`.
    llm_temperature: Annotated[float, Field(ge=0, le=_MAX_TEMPERATURE)] = 0.1

    @model_validator(mode="after")
    def _llm_values_fit_together(self) -> Self:
        if self.llm_attempt_timeout_ms > self.llm_budget_ms:
            raise _ATTEMPT_TIMEOUT_RULE.error()
        if self.llm_backoff_max_ms < self.llm_backoff_base_ms:
            raise _BACKOFF_MAXIMUM_RULE.error()
        return self


@dataclass(frozen=True, slots=True)
class _SettingRule:
    # A rule across settings names its setting in the context, because its error has no field.
    error_type: LiteralString
    message: LiteralString
    setting_name: str

    def error(self) -> PydanticCustomError:
        return PydanticCustomError(self.error_type, self.message, {"setting": self.setting_name})


_ATTEMPT_TIMEOUT_RULE = _SettingRule(
    "attempt_timeout_above_budget",
    "One attempt must fit in the budget of the LLM step",
    "llm_attempt_timeout_ms",
)
_BACKOFF_MAXIMUM_RULE = _SettingRule(
    "backoff_maximum_below_base",
    "The longest backoff must not be shorter than the first one",
    "llm_backoff_max_ms",
)
