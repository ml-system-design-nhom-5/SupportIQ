"""Tests of the `backend` command line and of settings loading (ARCH-34)."""

from pathlib import Path

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.composition_root.cli import (
    EXIT_FAILURE,
    EXIT_SETTINGS_INVALID,
    EXIT_SUCCESS,
    parse_arguments,
    report_failure,
    run_command,
)
from app.composition_root.command_arguments import (
    OneOffArguments,
    OneOffCommand,
    ServeArguments,
)
from app.composition_root.process_logging import build_redactor
from app.composition_root.settings_loading import (
    SettingRequiredError,
    require_setting,
)
from app.platform import DatabaseUnavailableError, EventName
from app.platform.adapters.database import DatabaseCaFileError
from app.platform.adapters.database_roles import AppRoleUrlError
from app.platform.adapters.telemetry import RedactingSpanProcessor
from app.platform.settings import DatabaseTls, TraceExporter
from app.pseudonymization.domain import NamedEntityModelMissingError
from tests.unit.platform.fakes import RecordingEventRecorder
from tests.unit.platform.settings_builders import build_test_settings

PORT = 8000
OTLP_ENDPOINT = "http://collector.test:4318/v1/traces"
GRACEFUL_SHUTDOWN_S = 20
OWNER_URL = "postgresql+asyncpg://supportiq_owner:owner-test-password@127.0.0.1:5433/supportiq"
CA_FILE_REFUSED = {"setting_names": "database_ca_file"}


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


def test_seed_with_if_empty_skips_a_seeded_database() -> None:
    arguments = parse_arguments(["seed", "--if-empty"])

    assert arguments == OneOffArguments(
        command=OneOffCommand.SEED, should_skip_seeded_database=True
    )


def test_reset_takes_no_if_empty_flag() -> None:
    with pytest.raises(SystemExit) as caught:
        parse_arguments(["reset", "--if-empty"])

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

    def provider_with_exporter(_exporter: SpanExporter | None) -> TracerProvider:
        return provider

    monkeypatch.setattr("app.composition_root.cli.create_tracer_provider", provider_with_exporter)
    events = RecordingEventRecorder()

    status = run_command(OneOffArguments(OneOffCommand.MIGRATE), build_test_settings(), events)

    (span,) = exporter.get_finished_spans()
    assert status == EXIT_SETTINGS_INVALID
    assert span.name == "migrate"
    assert span.status.status_code is StatusCode.ERROR


def test_a_one_off_command_exports_no_span_even_when_the_settings_choose_otlp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporters: list[SpanExporter | None] = []

    def recording_provider(exporter: SpanExporter | None) -> TracerProvider:
        exporters.append(exporter)
        return TracerProvider()

    monkeypatch.setattr("app.composition_root.cli.create_tracer_provider", recording_provider)
    settings = build_test_settings(
        trace_exporter=TraceExporter.OTLP, otlp_traces_endpoint=OTLP_ENDPOINT
    )

    run_command(OneOffArguments(OneOffCommand.MIGRATE), settings, RecordingEventRecorder())

    # ADR-0010, Egress control, item 3: a one-off command connects only to the database.
    assert exporters == [None]


def test_serve_gives_uvicorn_the_graceful_shutdown_of_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def record_run(_app: object, **options: object) -> None:
        calls.append(options)

    monkeypatch.setattr("app.composition_root.cli.uvicorn.run", record_run)
    settings = build_test_settings(graceful_shutdown_timeout_ms=GRACEFUL_SHUTDOWN_S * 1_000)

    status = run_command(
        ServeArguments(host="127.0.0.1", port=PORT), settings, RecordingEventRecorder()
    )

    assert status == EXIT_SUCCESS
    assert calls[0]["timeout_graceful_shutdown"] == GRACEFUL_SHUTDOWN_S


def test_serve_without_the_named_entity_model_stops_before_uvicorn_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def missing_model() -> None:
        raise NamedEntityModelMissingError

    def record_run(_app: object, **options: object) -> None:
        calls.append(options)

    # The loader is replaced, not its cache, so later tests still share the one model.
    monkeypatch.setattr(
        "app.composition_root.suggestions_wiring.load_named_entity_detector",
        missing_model,
    )
    monkeypatch.setattr("app.composition_root.cli.uvicorn.run", record_run)
    events = RecordingEventRecorder()

    status = run_command(ServeArguments(host="127.0.0.1", port=PORT), build_test_settings(), events)

    (failed,) = events.of(EventName.COMMAND_FAILED)
    assert status == EXIT_FAILURE
    assert failed.attributes["error_type"] == "NamedEntityModelMissingError"
    assert calls == []


def test_serve_with_an_unusable_ca_file_stops_at_startup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict[str, object]] = []

    def record_run(_app: object, **options: object) -> None:
        calls.append(options)

    monkeypatch.setattr("app.composition_root.cli.uvicorn.run", record_run)
    settings = build_test_settings(
        database_tls=DatabaseTls.VERIFY_FULL, database_ca_file=tmp_path / "absent.crt"
    )
    events = RecordingEventRecorder()

    status = run_command(ServeArguments(host="127.0.0.1", port=PORT), settings, events)

    assert status == EXIT_SETTINGS_INVALID
    assert events.of(EventName.SETTINGS_INVALID)[0].attributes == CA_FILE_REFUSED
    assert calls == []


def test_migrate_with_an_unusable_ca_file_stops_before_it_connects(tmp_path: Path) -> None:
    settings = build_test_settings(
        database_url_owner=OWNER_URL,
        database_tls=DatabaseTls.VERIFY_FULL,
        database_ca_file=tmp_path / "absent.crt",
    )
    events = RecordingEventRecorder()

    status = run_command(OneOffArguments(OneOffCommand.MIGRATE), settings, events)

    assert status == EXIT_SETTINGS_INVALID
    assert events.of(EventName.SETTINGS_INVALID)[0].attributes == CA_FILE_REFUSED


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


def test_an_unusable_ca_file_is_reported_as_an_invalid_setting() -> None:
    events = RecordingEventRecorder()

    status = report_failure(DatabaseCaFileError(), events)

    assert status == EXIT_SETTINGS_INVALID
    assert events.of(EventName.SETTINGS_INVALID)[0].attributes == CA_FILE_REFUSED


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
