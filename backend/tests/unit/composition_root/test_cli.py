"""Tests of the `backend` command line and of settings loading (ARCH-34)."""

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from supportiq_backend.composition_root.cli import (
    EXIT_FAILURE,
    EXIT_SETTINGS_INVALID,
    EXIT_SUCCESS,
    OneOffArguments,
    OneOffCommand,
    ServeArguments,
    build_redactor,
    parse_arguments,
    report_failure,
    run_command,
)
from supportiq_backend.composition_root.settings_loading import (
    SettingRequiredError,
    require_setting,
)
from supportiq_backend.platform import DatabaseUnavailableError, EventName
from supportiq_backend.platform.adapters.database_roles import AppRoleUrlError
from supportiq_backend.platform.adapters.telemetry import RedactingSpanProcessor
from supportiq_backend.platform.settings import Settings
from tests.unit.platform.fakes import RecordingEventRecorder
from tests.unit.platform.settings_builders import build_test_settings

PORT = 8000


def test_serve_takes_the_host_and_the_port() -> None:
    arguments = parse_arguments(["serve", "--host", "127.0.0.1", "--port", str(PORT)])

    assert arguments == ServeArguments(host="127.0.0.1", port=PORT)


@pytest.mark.parametrize(
    ("argument", "command"),
    [
        ("create-app-role", OneOffCommand.CREATE_APP_ROLE),
        ("migrate", OneOffCommand.MIGRATE),
        ("seed", OneOffCommand.SEED),
        ("reset", OneOffCommand.RESET),
    ],
)
def test_database_commands_are_one_off_commands(argument: str, command: OneOffCommand) -> None:
    arguments = parse_arguments([argument])

    assert arguments == OneOffArguments(command=command)


def test_reset_with_yes_is_confirmed_in_advance() -> None:
    arguments = parse_arguments(["reset", "--yes"])

    assert arguments == OneOffArguments(command=OneOffCommand.RESET, is_confirmed=True)


def test_seed_takes_no_confirmation_flag() -> None:
    with pytest.raises(SystemExit) as caught:
        parse_arguments(["seed", "--yes"])

    assert caught.value.code == EXIT_SETTINGS_INVALID


@pytest.mark.parametrize(
    "value",
    ["ORD-20901", "TRK-1000000001", "TXN-10000001", "+84 90 123 4567", "person@example.com"],
)
def test_redactor_of_the_process_hides_every_documented_format(value: str) -> None:
    redacted = build_redactor().redact(f"before {value} after")

    assert value not in redacted


@pytest.mark.parametrize("answer", ["no", "", "YES", "y"])
def test_reset_runs_only_after_the_exact_answer(
    monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    def answering_input() -> str:
        return answer

    monkeypatch.setattr("builtins.input", answering_input)
    events = RecordingEventRecorder()

    status = run_command(OneOffArguments(OneOffCommand.RESET), build_test_settings(), events)

    assert status == EXIT_SUCCESS
    assert events.names() == (EventName.SEED_RESET_CANCELLED,)


def test_reset_without_an_answer_is_cancelled(monkeypatch: pytest.MonkeyPatch) -> None:
    def closed_input() -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", closed_input)
    events = RecordingEventRecorder()

    status = run_command(OneOffArguments(OneOffCommand.RESET), build_test_settings(), events)

    assert status == EXIT_SUCCESS
    assert events.names() == (EventName.SEED_RESET_CANCELLED,)


def test_failed_command_marks_its_span(monkeypatch: pytest.MonkeyPatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(RedactingSpanProcessor(SimpleSpanProcessor(exporter)))

    def provider_with_exporter(_settings: Settings) -> TracerProvider:
        return provider

    monkeypatch.setattr(
        "supportiq_backend.composition_root.cli.build_tracer_provider", provider_with_exporter
    )
    events = RecordingEventRecorder()

    status = run_command(OneOffArguments(OneOffCommand.MIGRATE), build_test_settings(), events)

    (span,) = exporter.get_finished_spans()
    assert status == EXIT_SETTINGS_INVALID
    assert span.name == "migrate"
    assert span.status.status_code is StatusCode.ERROR


def test_serve_without_a_port_stops_with_a_usage_error() -> None:
    with pytest.raises(SystemExit) as caught:
        parse_arguments(["serve", "--host", "127.0.0.1"])

    assert caught.value.code == EXIT_SETTINGS_INVALID


def test_missing_command_setting_is_reported_by_name() -> None:
    events = RecordingEventRecorder()

    status = report_failure(SettingRequiredError("database_url_owner"), events)

    assert status == EXIT_SETTINGS_INVALID
    assert events.of(EventName.SETTINGS_INVALID)[0].attributes == {
        "setting_names": "database_url_owner"
    }


def test_app_url_without_the_app_role_is_reported_as_an_invalid_setting() -> None:
    events = RecordingEventRecorder()

    status = report_failure(AppRoleUrlError(), events)

    assert status == EXIT_SETTINGS_INVALID
    assert events.of(EventName.SETTINGS_INVALID)[0].attributes == {
        "setting_names": "database_url_app"
    }


def test_database_failure_of_a_command_is_logged_once_with_its_type() -> None:
    events = RecordingEventRecorder()

    status = report_failure(DatabaseUnavailableError(), events)

    assert status == EXIT_FAILURE
    assert events.of(EventName.COMMAND_FAILED)[0].attributes == {
        "error_type": "DatabaseUnavailableError"
    }


def test_require_setting_returns_a_present_setting() -> None:
    value = require_setting("present", "database_url_owner")

    assert value == "present"


def test_require_setting_names_an_absent_setting() -> None:
    with pytest.raises(SettingRequiredError) as caught:
        require_setting(None, "seed_password_admin")

    assert caught.value.setting_name == "seed_password_admin"
