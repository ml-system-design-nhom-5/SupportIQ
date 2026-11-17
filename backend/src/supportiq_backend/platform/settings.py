"""The settings of backend: one typed class, validated at startup (ARCH-33 to ARCH-37, PY-43).

Only the composition root creates `Settings` and passes plain values on, so no other code
reads the environment. Every setting is listed with a comment in `backend/.env.example`. The
initial values come from the Settings tables of the backend foundation design and of the
backend ticket workflow design.
"""

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, LiteralString, Self

from pydantic import Field, HttpUrl, PositiveInt, SecretStr, field_validator, model_validator
from pydantic_core import PydanticCustomError
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DATABASE_URL_SCHEME = "postgresql+asyncpg://"
# The only query a database URL may hold. SQLAlchemy passes every query parameter to
# `asyncpg.connect`, which stops with a TypeError on any other name, such as `sslmode`
# (deploy guide, TLS to PostgreSQL).
_ALLOWED_DATABASE_URL_QUERIES: tuple[dict[str, str], ...] = ({}, {"ssl": "require"})
# An origin as browsers send it: a lowercase scheme and host, an optional port, and no path
# (RFC 6454). Comparison with the `Origin` header is exact.
_ORIGIN_PATTERN = re.compile(r"^https?://([a-z0-9.-]+|\[[0-9a-f:]+\])(:[0-9]{1,5})?$")
# The bounds of a password in `CreateSessionRequest` of the contract, so that a seeded
# account can always sign in.
_PASSWORD_MIN_LENGTH = 1
_PASSWORD_MAX_LENGTH = 128

type SeedPassword = Annotated[
    SecretStr | None,
    Field(min_length=_PASSWORD_MIN_LENGTH, max_length=_PASSWORD_MAX_LENGTH),
]


class HandlingModeSetting(StrEnum):
    """The handling mode that new shop tickets get, as the tickets feature names it."""

    ASSISTED = "assisted"
    MANUAL = "manual"


class TraceExporter(StrEnum):
    """Where finished trace spans go (ADR-0007).

    `none` keeps spans in the process only, so every request still has a trace ID. `otlp`
    exports them over OTLP/HTTP to `otlp_traces_endpoint`.
    """

    NONE = "none"
    OTLP = "otlp"


class Settings(BaseSettings):
    """Every setting of backend, read from environment variables of the same name."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="forbid", frozen=True)

    database_url_app: SecretStr
    database_url_owner: SecretStr | None = None
    database_connect_timeout_ms: PositiveInt = 3_000
    database_statement_timeout_ms: PositiveInt = 5_000
    database_lock_timeout_ms: PositiveInt = 3_000
    database_pool_timeout_ms: PositiveInt = 3_000
    session_idle_timeout_ms: PositiveInt = 1_800_000
    session_absolute_lifetime_ms: PositiveInt = 28_800_000
    session_touch_interval_ms: PositiveInt = 60_000
    session_cookie_secure: bool = True
    allowed_origins: Annotated[tuple[str, ...], NoDecode, Field(min_length=1)]
    sign_in_failure_limit: PositiveInt = 5
    sign_in_failure_window_ms: PositiveInt = 900_000
    sign_in_failure_delay_ms: PositiveInt = 2_000
    idempotency_retention_ms: PositiveInt = 86_400_000
    default_handling_mode: HandlingModeSetting = HandlingModeSetting.ASSISTED
    seed_password_customer: SeedPassword = None
    seed_password_staff: SeedPassword = None
    seed_password_manager: SeedPassword = None
    seed_password_admin: SeedPassword = None
    ai_service_base_url: HttpUrl
    # An empty token would send `Authorization: Bearer ` and fail every call (ERR-17).
    ai_service_token: Annotated[SecretStr, Field(min_length=1)]
    ai_service_analysis_timeout_ms: PositiveInt = 3_000
    ai_service_draft_timeout_ms: PositiveInt = 11_000
    ai_service_read_timeout_ms: PositiveInt = 3_000
    # The `backend_version` of `getAdminVersions`, from 1 to 64 characters (backend contract).
    backend_build_version: Annotated[str, Field(min_length=1, max_length=64)]
    suggestion_workers_per_replica: PositiveInt = 5
    suggestion_job_lease_ms: PositiveInt = 15_000
    suggestion_job_max_attempts: PositiveInt = 3
    suggestion_queue_poll_ms: PositiveInt = 500
    suggestion_events_poll_ms: PositiveInt = 1_000
    suggestion_events_max_ms: PositiveInt = 600_000
    # uvicorn takes whole seconds; after this wait it cancels every open response (ADR-0023).
    graceful_shutdown_timeout_ms: Annotated[PositiveInt, Field(multiple_of=1_000)] = 15_000
    trace_exporter: TraceExporter = TraceExporter.NONE
    otlp_traces_endpoint: HttpUrl | None = None
    otlp_export_timeout_ms: PositiveInt = 10_000

    @field_validator("database_url_app", "database_url_owner")
    @classmethod
    def _require_asyncpg_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        url = value.get_secret_value()
        if not _is_asyncpg_url(url):
            raise _ASYNCPG_URL_RULE.error()
        if dict(make_url(url).query) not in _ALLOWED_DATABASE_URL_QUERIES:
            raise _DATABASE_URL_QUERY_RULE.error()
        return value

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _decode_origins(cls, value: object) -> object:
        # The environment holds text. Decoding it here keeps a malformed value an error of this
        # setting: decoded by pydantic-settings, its error would name no setting (ARCH-34).
        if not isinstance(value, str):
            return value
        try:
            return json.loads(value)
        except ValueError as error:
            raise _ORIGIN_LIST_RULE.error() from error

    @field_validator("allowed_origins")
    @classmethod
    def _require_origins(cls, origins: tuple[str, ...]) -> tuple[str, ...]:
        if not all(_ORIGIN_PATTERN.fullmatch(origin) for origin in origins):
            raise _ORIGIN_RULE.error()
        return origins

    @model_validator(mode="after")
    def _check_related_settings(self) -> Self:
        if self.trace_exporter is TraceExporter.OTLP and self.otlp_traces_endpoint is None:
            raise _OTLP_ENDPOINT_RULE.error()
        if self.session_touch_interval_ms >= self.session_idle_timeout_ms:
            raise _TOUCH_INTERVAL_RULE.error()
        # A lease shorter than the draft call would let a second worker claim a running job
        # (ADR-0011, Suggestion job queue, item 3).
        if self.suggestion_job_lease_ms <= self.ai_service_draft_timeout_ms:
            raise _LEASE_RULE.error()
        return self


@dataclass(frozen=True, slots=True)
class _SettingRule:
    error_type: LiteralString
    message: LiteralString
    setting_name: str | None = None

    def error(self) -> PydanticCustomError:
        context = None if self.setting_name is None else {"setting": self.setting_name}
        return PydanticCustomError(self.error_type, self.message, context)


_ASYNCPG_URL_RULE = _SettingRule(
    "database_url_format", "The value must be a well-formed URL that uses postgresql+asyncpg"
)
_DATABASE_URL_QUERY_RULE = _SettingRule(
    "database_url_query", "The query of the URL may hold only ssl=require"
)
_ORIGIN_LIST_RULE = _SettingRule("origin_list_format", "The value must be a JSON list of origins")
_ORIGIN_RULE = _SettingRule(
    "origin_format", "Each allowed origin is a lowercase scheme, host, and optional port"
)
# Rules across settings name the setting in their context, because their error has no field.
_OTLP_ENDPOINT_RULE = _SettingRule(
    "setting_required", "Required when trace_exporter is otlp", "otlp_traces_endpoint"
)
_TOUCH_INTERVAL_RULE = _SettingRule(
    "setting_too_large",
    "Must be shorter than session_idle_timeout_ms",
    "session_touch_interval_ms",
)


_LEASE_RULE = _SettingRule(
    "setting_too_small",
    "Must be longer than ai_service_draft_timeout_ms",
    "suggestion_job_lease_ms",
)


def _is_asyncpg_url(url: str) -> bool:
    # The error of `make_url` can repeat part of the URL, so it never reaches the caller.
    try:
        make_url(url)
    except ArgumentError, ValueError:
        return False
    return url.startswith(DATABASE_URL_SCHEME)
