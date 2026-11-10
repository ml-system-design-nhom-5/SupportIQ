"""The `backend` command: run a replica, or run one of the one-off database commands.

Every subcommand reads the settings first and stops with status 2, after logging
`settings.invalid` with the names of the bad settings, when one is missing or invalid
(ARCH-34). The one-off commands run as the owner, never at replica startup (ADR-0011,
`backend` replicas, statements 2 and 3).
"""

import argparse
import asyncio
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

import uvicorn

from supportiq_backend.commerce import (
    ORDER_ID_PATTERN,
    PHONE_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
)
from supportiq_backend.composition_root.database_commands import create_app_role, migrate
from supportiq_backend.composition_root.runtime import build_tracer_provider
from supportiq_backend.composition_root.seed_commands import reset, seed
from supportiq_backend.composition_root.settings_loading import (
    SettingRequiredError,
    SettingsInvalidError,
    load_settings,
)
from supportiq_backend.composition_root.web_application import create_app
from supportiq_backend.platform import BackendError, EventName, EventRecorder
from supportiq_backend.platform.adapters.database_roles import AppRoleUrlError
from supportiq_backend.platform.adapters.logging_setup import (
    GENERIC_REDACTION_PATTERNS,
    Redactor,
    StandardLibraryEventRecorder,
    configure_logging,
)
from supportiq_backend.platform.adapters.system_clock import SystemClock
from supportiq_backend.platform.adapters.telemetry import (
    OpenTelemetryTraceContext,
    create_tracer_provider,
)
from supportiq_backend.platform.settings import Settings

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_SETTINGS_INVALID = 2
TRACER_NAME = "supportiq_backend.commands"
LOAD_SETTINGS_SPAN = "load_settings"
SERVE_COMMAND = "serve"
_RESET_QUESTION = "Every backend table will be emptied and seeded again. Type yes to go on: "
_RESET_ANSWER = "yes"


class OneOffCommand(StrEnum):
    """The one-off database commands of `backend`, run as the database owner."""

    CREATE_APP_ROLE = "create-app-role"
    MIGRATE = "migrate"
    SEED = "seed"
    RESET = "reset"


@dataclass(frozen=True, slots=True)
class ServeArguments:
    """The arguments of `backend serve`.

    Attributes:
        host: The interface to listen on.
        port: The TCP port to listen on.
    """

    host: str
    port: int


@dataclass(frozen=True, slots=True)
class OneOffArguments:
    """The arguments of a one-off database command.

    Attributes:
        command: The command to run.
        is_confirmed: Whether `--yes` confirmed a reset in advance.
    """

    command: OneOffCommand
    is_confirmed: bool = False


type CommandArguments = ServeArguments | OneOffArguments


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `backend` command.

    Args:
        argv: The arguments after the program name; the process arguments when None.

    Returns:
        The exit status: 0 on success, 2 for missing or invalid settings, 1 for a failed
        command. `serve` can also end with a status of uvicorn.
    """
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    events = build_event_recorder()
    try:
        settings = _load_settings_in_a_span(events)
    except SettingsInvalidError:
        return EXIT_SETTINGS_INVALID
    return run_command(arguments, settings, events)


def report_failure(error: BackendError, events: EventRecorder) -> int:
    """Log a failure of a command once and turn it into an exit status (PY-21, ERR-05).

    Args:
        error: The failure.
        events: Where the failure is logged.

    Returns:
        2 for a missing or invalid setting, 1 for any other failure.
    """
    match error:
        case SettingRequiredError():
            events.record(EventName.SETTINGS_INVALID, setting_names=error.setting_name)
            return EXIT_SETTINGS_INVALID
        case AppRoleUrlError():
            events.record(EventName.SETTINGS_INVALID, setting_names="database_url_app")
            return EXIT_SETTINGS_INVALID
        case _:
            events.record(EventName.COMMAND_FAILED, error_type=type(error).__name__)
            return EXIT_FAILURE


def run_command(arguments: CommandArguments, settings: Settings, events: EventRecorder) -> int:
    """Run one subcommand with validated settings.

    Args:
        arguments: The parsed arguments.
        settings: The validated settings.
        events: The event recorder of the process.

    Returns:
        The exit status.
    """
    match arguments:
        case ServeArguments():
            app = create_app(settings, events, SystemClock())
            uvicorn.run(
                app,
                host=arguments.host,
                port=arguments.port,
                log_config=None,
                access_log=False,
                server_header=False,
            )
            return EXIT_SUCCESS
        case OneOffArguments():
            return _run_one_off(arguments, settings, events)
        case _:
            assert_never(arguments)


def build_event_recorder() -> EventRecorder:
    """Send every log record of the process to standard output as JSON lines (LOG-02).

    Returns:
        The event recorder of the process.
    """
    return StandardLibraryEventRecorder(configure_logging(sys.stdout, build_redactor()))


def build_redactor() -> Redactor:
    """Combine the generic patterns with the documented ID formats of commerce (LOG-30).

    Returns:
        The redactor of every log line.
    """
    return Redactor(
        (
            *GENERIC_REDACTION_PATTERNS,
            ORDER_ID_PATTERN,
            TRACKING_CODE_PATTERN,
            TRANSACTION_ID_PATTERN,
            PHONE_PATTERN,
        )
    )


def parse_arguments(argv: Sequence[str]) -> CommandArguments:
    """Parse the command line.

    Args:
        argv: The arguments after the program name.

    Returns:
        The arguments of the chosen subcommand.
    """
    parser = argparse.ArgumentParser(prog="backend", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser(SERVE_COMMAND, help="Run one backend replica.")
    serve.add_argument("--host", required=True, help="The interface to listen on.")
    serve.add_argument("--port", required=True, type=int, help="The TCP port to listen on.")
    commands.add_parser(
        OneOffCommand.CREATE_APP_ROLE.value,
        help="Create or update the role supportiq_app, as the database owner.",
    )
    commands.add_parser(
        OneOffCommand.MIGRATE.value,
        help="Apply every database migration, as the database owner.",
    )
    commands.add_parser(
        OneOffCommand.SEED.value,
        help="Load the seed file into an empty database, as the database owner.",
    )
    reset_parser = commands.add_parser(
        OneOffCommand.RESET.value,
        help="Empty every backend table and seed again, as the database owner.",
    )
    reset_parser.add_argument("--yes", action="store_true", help="Skip the confirmation.")
    namespace = parser.parse_args(argv)
    if namespace.command == SERVE_COMMAND:
        return ServeArguments(host=str(namespace.host), port=int(namespace.port))
    return OneOffArguments(
        command=OneOffCommand(str(namespace.command)),
        is_confirmed=bool(getattr(namespace, "yes", False)),
    )


def _load_settings_in_a_span(events: EventRecorder) -> Settings:
    # The settings choose the exporter, so this first span of the process exports nothing; it
    # gives the lines of settings their trace ID (LOG-06). `serve` runs outside it, because
    # requests inherit the current span, and each request is a trace of its own.
    tracer = create_tracer_provider(None).get_tracer(TRACER_NAME)
    with tracer.start_as_current_span(LOAD_SETTINGS_SPAN):
        return load_settings(events)


def _run_one_off(arguments: OneOffArguments, settings: Settings, events: EventRecorder) -> int:
    # Work outside a request starts its own span, so all its log lines, a failure included,
    # carry a trace ID (LOG-06).
    tracer_provider = build_tracer_provider(settings)
    span_name = arguments.command.value.replace("-", "_")
    try:
        with tracer_provider.get_tracer(TRACER_NAME).start_as_current_span(span_name):
            return _run_work(arguments, settings, events)
    finally:
        tracer_provider.shutdown()


def _run_work(arguments: OneOffArguments, settings: Settings, events: EventRecorder) -> int:
    try:
        match arguments.command:
            case OneOffCommand.CREATE_APP_ROLE:
                asyncio.run(create_app_role(settings, events))
            case OneOffCommand.MIGRATE:
                asyncio.run(migrate(settings, events))
            case OneOffCommand.SEED:
                asyncio.run(seed(settings, events))
            case OneOffCommand.RESET:
                _reset_after_confirmation(arguments, settings, events)
            case _:
                assert_never(arguments.command)
    except BackendError as error:
        OpenTelemetryTraceContext().record_failure(error)
        return report_failure(error, events)
    return EXIT_SUCCESS


def _reset_after_confirmation(
    arguments: OneOffArguments, settings: Settings, events: EventRecorder
) -> None:
    if arguments.is_confirmed or _ask_to_confirm_reset():
        asyncio.run(reset(settings, events))
    else:
        events.record(EventName.SEED_RESET_CANCELLED)


def _ask_to_confirm_reset() -> bool:
    # The question goes to standard error, so standard output holds only JSON lines (LOG-02).
    sys.stderr.write(_RESET_QUESTION)
    sys.stderr.flush()
    try:
        return input().strip() == _RESET_ANSWER
    except EOFError:
        return False
