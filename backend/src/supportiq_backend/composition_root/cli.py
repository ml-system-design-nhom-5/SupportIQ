"""The `backend` command: run a replica, or run one of the one-off commands.

Every subcommand reads the settings first and stops with status 2, after logging
`settings.invalid` with the names of the bad settings, when one is missing or invalid
(ARCH-34). The one-off database commands run as the owner, never at replica startup (ADR-0011,
`backend` replicas, statements 2 and 3). `export-decisions` only reads, so it runs as
`supportiq_app` (backend ticket workflow design, The decision-record export).
"""

import argparse
import asyncio
import sys
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import assert_never

import uvicorn

from supportiq_backend.composition_root.command_arguments import (
    OneOffArguments,
    OneOffCommand,
    ServeArguments,
)
from supportiq_backend.composition_root.database_commands import create_app_role, migrate
from supportiq_backend.composition_root.process_logging import build_event_recorder
from supportiq_backend.composition_root.report_commands import (
    EXPORT_DECISIONS_COMMAND,
    EXPORT_DECISIONS_HELP,
    ExportDecisionsArguments,
    add_export_decisions_arguments,
    export_decisions,
    to_export_decisions_arguments,
)
from supportiq_backend.composition_root.seed_commands import reset, seed
from supportiq_backend.composition_root.settings_loading import (
    SettingRequiredError,
    SettingsInvalidError,
    load_settings,
)
from supportiq_backend.composition_root.web_application import create_app
from supportiq_backend.platform import BackendError, EventName, EventRecorder
from supportiq_backend.platform.adapters.database_roles import AppRoleUrlError
from supportiq_backend.platform.adapters.system_clock import SystemClock
from supportiq_backend.platform.adapters.telemetry import (
    OpenTelemetryTraceContext,
    create_tracer_provider,
)
from supportiq_backend.platform.settings import Settings
from supportiq_backend.reports import ExportPathRefusedError

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_SETTINGS_INVALID = 2
TRACER_NAME = "supportiq_backend.commands"
LOAD_SETTINGS_SPAN = "load_settings"
SERVE_COMMAND = "serve"
_RESET_QUESTION = "Every backend table will be emptied and seeded again. Type yes to go on: "
_RESET_ANSWER = "yes"


type CommandArguments = ServeArguments | OneOffArguments | ExportDecisionsArguments


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

    A refused export path is also written to standard error, because the person needs it to
    correct the command, and standard output holds only JSON lines (LOG-02).

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
        case ExportPathRefusedError():
            # The person needs the refused path to correct it. Standard output holds only JSON
            # lines (LOG-02), so the message goes to standard error, as the reset question does.
            sys.stderr.write(error.detail + "\n")
            events.record(EventName.COMMAND_FAILED, error_type=type(error).__name__)
            return EXIT_FAILURE
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
            work = partial(_run_database_command, arguments, settings, events)
            return _run_one_off(arguments.command.value, events, work)
        case ExportDecisionsArguments():
            work = partial(_export_decisions, arguments, settings, events)
            return _run_one_off(EXPORT_DECISIONS_COMMAND, events, work)
        case _:
            assert_never(arguments)


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
    export_parser = commands.add_parser(EXPORT_DECISIONS_COMMAND, help=EXPORT_DECISIONS_HELP)
    add_export_decisions_arguments(export_parser)
    namespace = parser.parse_args(argv)
    if namespace.command == SERVE_COMMAND:
        return ServeArguments(host=str(namespace.host), port=int(namespace.port))
    if namespace.command == EXPORT_DECISIONS_COMMAND:
        return to_export_decisions_arguments(namespace, export_parser)
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


def _run_one_off(command_name: str, events: EventRecorder, work: Callable[[], None]) -> int:
    # Work outside a request starts its own span, so all its log lines, a failure included,
    # carry a trace ID (LOG-06). The span never leaves the process: a one-off command connects
    # only to the database (ADR-0010, Egress control, item 3; SEC-40).
    tracer_provider = create_tracer_provider(None)
    span_name = command_name.replace("-", "_")
    try:
        with tracer_provider.get_tracer(TRACER_NAME).start_as_current_span(span_name):
            return _run_work(work, events)
    finally:
        tracer_provider.shutdown()


def _run_work(work: Callable[[], None], events: EventRecorder) -> int:
    try:
        work()
    except BackendError as error:
        OpenTelemetryTraceContext().record_failure(error)
        return report_failure(error, events)
    return EXIT_SUCCESS


def _run_database_command(
    arguments: OneOffArguments, settings: Settings, events: EventRecorder
) -> None:
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


def _export_decisions(
    arguments: ExportDecisionsArguments, settings: Settings, events: EventRecorder
) -> None:
    # `exports/` belongs to the working directory of the command (SEC-33).
    asyncio.run(export_decisions(settings, events, arguments, working_directory=Path.cwd()))


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
