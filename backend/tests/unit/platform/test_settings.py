"""Tests of the settings: names, initial values, and validation (ARCH-33 to ARCH-37, PY-44)."""

import pytest
from pydantic import SecretStr, ValidationError

from supportiq_backend.composition_root.settings_loading import invalid_setting_names
from supportiq_backend.platform.settings import HandlingModeSetting, Settings, TraceExporter
from tests.unit.platform.settings_builders import (
    TEST_AI_SERVICE_TOKEN,
    TEST_AI_SERVICE_URL,
    TEST_APP_URL,
    TEST_BUILD_VERSION,
    TEST_ORIGIN,
    SettingsWithoutEnvironment,
    build_test_settings,
)

APP_URL = TEST_APP_URL
REQUIRED_VALUES: dict[str, object] = {
    "database_url_app": APP_URL,
    "allowed_origins": (TEST_ORIGIN,),
    "ai_service_base_url": TEST_AI_SERVICE_URL,
    "ai_service_token": TEST_AI_SERVICE_TOKEN,
    "backend_build_version": TEST_BUILD_VERSION,
}
SEED_PASSWORD = "seed-test-password"
IDLE_TIMEOUT_MS = 60_000
DRAFT_TIMEOUT_MS = 11_000
build_settings = build_test_settings


def names_of_invalid_settings(**values: object) -> tuple[str, ...]:
    with pytest.raises(ValidationError) as caught:
        SettingsWithoutEnvironment.model_validate(values)
    return invalid_setting_names(caught.value)


@pytest.mark.parametrize(
    ("setting_name", "initial_value"),
    [
        ("database_url_owner", None),
        ("database_connect_timeout_ms", 3_000),
        ("database_statement_timeout_ms", 5_000),
        ("database_lock_timeout_ms", 3_000),
        ("database_pool_timeout_ms", 3_000),
        ("session_idle_timeout_ms", 1_800_000),
        ("session_absolute_lifetime_ms", 28_800_000),
        ("session_touch_interval_ms", 60_000),
        ("session_cookie_secure", True),
        ("sign_in_failure_limit", 5),
        ("sign_in_failure_window_ms", 900_000),
        ("sign_in_failure_delay_ms", 2_000),
        ("idempotency_retention_ms", 86_400_000),
        ("default_handling_mode", HandlingModeSetting.ASSISTED),
        ("seed_password_customer", None),
        ("seed_password_staff", None),
        ("seed_password_manager", None),
        ("seed_password_admin", None),
        ("trace_exporter", TraceExporter.NONE),
        ("otlp_traces_endpoint", None),
        ("otlp_export_timeout_ms", 10_000),
        ("ai_service_analysis_timeout_ms", 3_000),
        ("ai_service_draft_timeout_ms", 11_000),
        ("ai_service_read_timeout_ms", 3_000),
        ("suggestion_workers_per_replica", 5),
        ("suggestion_job_lease_ms", 15_000),
        ("suggestion_job_max_attempts", 3),
        ("suggestion_queue_poll_ms", 500),
    ],
)
def test_settings_start_with_the_initial_values_of_the_design(
    setting_name: str, initial_value: object
) -> None:
    settings = build_settings()

    value = getattr(settings, setting_name)

    assert value == initial_value


def test_settings_name_every_required_setting_when_they_are_missing() -> None:
    names = names_of_invalid_settings()

    assert names == (
        "database_url_app",
        "allowed_origins",
        "ai_service_base_url",
        "ai_service_token",
        "backend_build_version",
    )


@pytest.mark.parametrize("lease_ms", [DRAFT_TIMEOUT_MS, DRAFT_TIMEOUT_MS - 1])
def test_settings_refuse_a_lease_that_is_not_longer_than_the_draft_timeout(
    lease_ms: int,
) -> None:
    names = names_of_invalid_settings(
        **REQUIRED_VALUES,
        suggestion_job_lease_ms=lease_ms,
        ai_service_draft_timeout_ms=DRAFT_TIMEOUT_MS,
    )

    assert names == ("suggestion_job_lease_ms",)


def test_settings_accept_a_lease_one_millisecond_longer_than_the_draft_timeout() -> None:
    settings = build_settings(
        suggestion_job_lease_ms=DRAFT_TIMEOUT_MS + 1, ai_service_draft_timeout_ms=DRAFT_TIMEOUT_MS
    )

    assert settings.suggestion_job_lease_ms == DRAFT_TIMEOUT_MS + 1


def test_the_service_token_stays_out_of_the_repr_of_the_settings() -> None:
    settings = build_settings()

    assert TEST_AI_SERVICE_TOKEN not in repr(settings)


@pytest.mark.parametrize(
    ("setting_name", "invalid_value"),
    [
        ("database_url_app", "postgresql://supportiq_app:pw@127.0.0.1:5433/supportiq"),
        ("database_url_owner", "sqlite:///supportiq.db"),
        ("database_connect_timeout_ms", 0),
        ("database_statement_timeout_ms", -1),
        ("database_lock_timeout_ms", "soon"),
        ("database_pool_timeout_ms", 0),
        ("session_idle_timeout_ms", 0),
        ("session_absolute_lifetime_ms", 0),
        ("session_cookie_secure", "sometimes"),
        ("database_url_app", "postgresql+asyncpg://u:p@127.0.0.1:notaport/supportiq"),
        ("database_url_owner", "postgresql+asyncpg://u:p@127.0.0.1:notaport/supportiq"),
        ("allowed_origins", ()),
        ("allowed_origins", ("http://localhost:5173/",)),
        ("allowed_origins", ("HTTP://LOCALHOST:5173",)),
        ("allowed_origins", ("localhost:5173",)),
        ("sign_in_failure_limit", 0),
        ("sign_in_failure_window_ms", 0),
        ("sign_in_failure_delay_ms", 0),
        ("idempotency_retention_ms", 0),
        ("default_handling_mode", "automatic"),
        ("seed_password_admin", ""),
        ("ai_service_token", ""),
        ("ai_service_base_url", "not a url"),
        ("backend_build_version", ""),
        ("backend_build_version", "x" * 65),
        ("seed_password_staff", "x" * 129),
        ("trace_exporter", "zipkin"),
        ("otlp_traces_endpoint", "not a url"),
        ("otlp_export_timeout_ms", 0),
    ],
)
def test_settings_name_the_one_invalid_setting(setting_name: str, invalid_value: object) -> None:
    names = names_of_invalid_settings(**(REQUIRED_VALUES | {setting_name: invalid_value}))

    assert names == (setting_name,)


def test_settings_require_the_otlp_endpoint_when_the_exporter_is_otlp() -> None:
    names = names_of_invalid_settings(**(REQUIRED_VALUES | {"trace_exporter": "otlp"}))

    assert names == ("otlp_traces_endpoint",)


def test_settings_accept_the_otlp_exporter_with_an_endpoint() -> None:
    settings = build_settings(
        trace_exporter="otlp", otlp_traces_endpoint="http://collector:4318/v1/traces"
    )

    assert str(settings.otlp_traces_endpoint) == "http://collector:4318/v1/traces"


def test_settings_refuse_a_touch_interval_equal_to_the_idle_timeout() -> None:
    names = names_of_invalid_settings(
        **(
            REQUIRED_VALUES
            | {
                "session_touch_interval_ms": IDLE_TIMEOUT_MS,
                "session_idle_timeout_ms": IDLE_TIMEOUT_MS,
            }
        )
    )

    assert names == ("session_touch_interval_ms",)


def test_settings_accept_a_touch_interval_just_below_the_idle_timeout() -> None:
    touch_interval_ms = IDLE_TIMEOUT_MS - 1

    settings = build_settings(
        session_touch_interval_ms=touch_interval_ms, session_idle_timeout_ms=IDLE_TIMEOUT_MS
    )

    assert settings.session_touch_interval_ms == touch_interval_ms


def test_settings_accept_ipv6_and_https_origins() -> None:
    settings = build_settings(allowed_origins=("https://supportiq.example", "http://[::1]:5173"))

    assert settings.allowed_origins == ("https://supportiq.example", "http://[::1]:5173")


def test_settings_never_show_a_secret_in_their_repr() -> None:
    settings = build_settings(
        database_url_owner=APP_URL.replace("supportiq_app", "supportiq_owner"),
        seed_password_admin=SEED_PASSWORD,
    )

    text = repr(settings)

    assert "app-test-password" not in text
    assert SEED_PASSWORD not in text
    assert isinstance(settings.seed_password_admin, SecretStr)


def test_settings_decode_the_origins_of_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL_APP", TEST_APP_URL)
    monkeypatch.setenv("AI_SERVICE_BASE_URL", TEST_AI_SERVICE_URL)
    monkeypatch.setenv("AI_SERVICE_TOKEN", TEST_AI_SERVICE_TOKEN)
    monkeypatch.setenv("BACKEND_BUILD_VERSION", TEST_BUILD_VERSION)
    monkeypatch.setenv("ALLOWED_ORIGINS", '["http://localhost:5173", "https://shop.example"]')

    settings = Settings.model_validate({})

    assert settings.allowed_origins == ("http://localhost:5173", "https://shop.example")


@pytest.mark.parametrize("value", ["[http://localhost:5173]", "http://localhost:5173", ""])
def test_malformed_origins_of_the_environment_name_their_setting(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("DATABASE_URL_APP", TEST_APP_URL)
    monkeypatch.setenv("AI_SERVICE_BASE_URL", TEST_AI_SERVICE_URL)
    monkeypatch.setenv("AI_SERVICE_TOKEN", TEST_AI_SERVICE_TOKEN)
    monkeypatch.setenv("BACKEND_BUILD_VERSION", TEST_BUILD_VERSION)
    monkeypatch.setenv("ALLOWED_ORIGINS", value)

    with pytest.raises(ValidationError) as caught:
        Settings.model_validate({})

    assert invalid_setting_names(caught.value) == ("allowed_origins",)
