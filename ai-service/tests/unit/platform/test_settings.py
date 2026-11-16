"""Startup reads the settings from the environment and stops on invalid ones (ARCH-34)."""

from pathlib import Path

import pytest

from supportiq_ai_service.composition_root.settings_loading import (
    SettingsInvalidError,
    load_settings,
)
from supportiq_ai_service.platform import EventName
from tests.unit.platform.fakes import LLM_ENVIRONMENT, RecordingEventRecorder

SERVICE_TOKEN_VARIABLE = "SERVICE_TOKEN"
SERVICE_TOKEN = "service-token-for-unit-tests"
RELEASE_MANIFEST_PATH_VARIABLE = "RELEASE_MANIFEST_PATH"
RELEASE_MANIFEST_PATH = "/srv/release/release-manifest.json"


@pytest.fixture(autouse=True)
def required_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RELEASE_MANIFEST_PATH_VARIABLE, RELEASE_MANIFEST_PATH)
    for name, value in LLM_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)


def test_valid_settings_are_loaded_and_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    events = RecordingEventRecorder()

    settings = load_settings(events)

    assert settings.service_token.get_secret_value() == SERVICE_TOKEN
    assert settings.release_manifest_path == Path(RELEASE_MANIFEST_PATH)
    assert events.names() == (EventName.SETTINGS_LOADED,)


def test_a_missing_release_manifest_path_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.delenv(RELEASE_MANIFEST_PATH_VARIABLE)
    events = RecordingEventRecorder()

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(events)

    assert raised.value.setting_names == ("release_manifest_path",)
    (invalid,) = events.of(EventName.SETTINGS_INVALID)
    assert invalid.attributes == {"setting_names": "release_manifest_path"}


@pytest.mark.parametrize("value", [None, ""])
def test_a_missing_or_empty_service_token_stops_startup_without_its_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(SERVICE_TOKEN_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, value)
    events = RecordingEventRecorder()

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(events)

    assert raised.value.setting_names == ("service_token",)
    (invalid,) = events.of(EventName.SETTINGS_INVALID)
    assert invalid.attributes == {"setting_names": "service_token"}


def test_the_service_token_never_appears_in_the_repr_of_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)

    settings = load_settings(RecordingEventRecorder())

    assert SERVICE_TOKEN not in repr(settings)


def test_the_llm_settings_have_the_budget_of_nfr_07_and_the_values_of_main(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)

    settings = load_settings(RecordingEventRecorder())

    assert settings.gemini_api_key.get_secret_value() == LLM_ENVIRONMENT["GEMINI_API_KEY"]
    assert LLM_ENVIRONMENT["GEMINI_API_KEY"] not in repr(settings)
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert (
        settings.llm_input_price_micro_usd_per_million_tokens,
        settings.llm_output_price_micro_usd_per_million_tokens,
    ) == (1000, 2000)
    assert (
        settings.llm_budget_ms,
        settings.llm_attempt_timeout_ms,
        settings.llm_max_attempts,
        settings.llm_backoff_base_ms,
        settings.llm_backoff_max_ms,
        settings.llm_max_output_tokens,
        settings.llm_temperature,
    ) == (10_000, 5_000, 2, 250, 2_000, 1_024, 0.1)


@pytest.mark.parametrize(
    "name",
    [
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS",
        "LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS",
    ],
)
def test_a_missing_llm_setting_without_default_stops_startup(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.delenv(name)

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(RecordingEventRecorder())

    assert raised.value.setting_names == (name.lower(),)


@pytest.mark.parametrize(
    ("name", "value", "invalid_setting"),
    [
        ("GEMINI_API_KEY", "", "gemini_api_key"),
        ("GEMINI_MODEL", "gpt-4o", "gemini_model"),
        (
            "LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS",
            "-1",
            "llm_input_price_micro_usd_per_million_tokens",
        ),
        ("LLM_BUDGET_MS", "10001", "llm_budget_ms"),
        ("LLM_MAX_ATTEMPTS", "4", "llm_max_attempts"),
        ("LLM_MAX_ATTEMPTS", "0", "llm_max_attempts"),
        ("LLM_TEMPERATURE", "2.5", "llm_temperature"),
        ("LLM_ATTEMPT_TIMEOUT_MS", "10000", "llm_attempt_timeout_ms"),
        ("LLM_BACKOFF_BASE_MS", "0", "llm_backoff_base_ms"),
        ("GROUNDING_UNCITED_SEGMENT_MAX_CHARS", "41", "grounding_uncited_segment_max_chars"),
        ("GROUNDING_UNCITED_SEGMENT_MAX_CHARS", "0", "grounding_uncited_segment_max_chars"),
        ("RETRIEVAL_TOP_K_DOCUMENTS", "0", "retrieval_top_k_documents"),
        ("MODEL_CPU_THREADS", "0", "model_cpu_threads"),
    ],
)
def test_an_llm_setting_out_of_its_range_stops_startup(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str, invalid_setting: str
) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.setenv("LLM_BUDGET_MS", "8000")
    monkeypatch.setenv(name, value)

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(RecordingEventRecorder())

    assert raised.value.setting_names == (invalid_setting,)


def test_an_attempt_as_long_as_the_budget_is_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.setenv("LLM_BUDGET_MS", "8000")
    monkeypatch.setenv("LLM_ATTEMPT_TIMEOUT_MS", "8000")

    settings = load_settings(RecordingEventRecorder())

    assert (settings.llm_budget_ms, settings.llm_attempt_timeout_ms) == (8000, 8000)


def test_a_backoff_maximum_below_its_base_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.setenv("LLM_BACKOFF_BASE_MS", "500")
    monkeypatch.setenv("LLM_BACKOFF_MAX_MS", "400")

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(RecordingEventRecorder())

    assert raised.value.setting_names == ("llm_backoff_max_ms",)


def test_the_pipeline_settings_have_the_values_of_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)

    settings = load_settings(RecordingEventRecorder())

    assert (
        settings.retrieval_top_k_documents,
        settings.retrieval_max_chunks_per_document,
        settings.retrieval_token_budget_tokens,
        settings.grounding_uncited_segment_max_chars,
        settings.model_cpu_threads,
    ) == (3, 2, 1_500, 40, 2)


def _set_prices(monkeypatch: pytest.MonkeyPatch, input_price: str, output_price: str) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.setenv("LLM_INPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS", input_price)
    monkeypatch.setenv("LLM_OUTPUT_PRICE_MICRO_USD_PER_MILLION_TOKENS", output_price)


def test_two_prices_that_sum_to_the_cost_cap_of_the_contract_are_valid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_prices(monkeypatch, "9999999", "1")

    settings = load_settings(RecordingEventRecorder())

    assert (
        settings.llm_input_price_micro_usd_per_million_tokens,
        settings.llm_output_price_micro_usd_per_million_tokens,
    ) == (9_999_999, 1)


def test_two_prices_above_the_cost_cap_of_the_contract_stop_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_prices(monkeypatch, "10000000", "1")

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(RecordingEventRecorder())

    assert raised.value.setting_names == ("llm_output_price_micro_usd_per_million_tokens",)
