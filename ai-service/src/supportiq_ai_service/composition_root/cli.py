"""The `ai-service` command: run one replica.

It reads the settings first and stops with status 2, after logging `settings.invalid` with
the names of the bad settings, when one is missing or invalid (ARCH-34).
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

import uvicorn

from supportiq_ai_service.composition_root.settings_loading import (
    SettingsInvalidError,
    load_settings,
)
from supportiq_ai_service.composition_root.web_application import create_app
from supportiq_ai_service.platform import EventRecorder
from supportiq_ai_service.platform.adapters.logging_setup import (
    GENERIC_REDACTION_PATTERNS,
    Redactor,
    StandardLibraryEventRecorder,
    configure_logging,
)
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.release.adapters import NoReleaseSource

EXIT_SUCCESS = 0
EXIT_SETTINGS_INVALID = 2
SERVE_COMMAND = "serve"


@dataclass(frozen=True, slots=True)
class ServeArguments:
    """The arguments of `ai-service serve`.

    Attributes:
        host: The interface to listen on.
        port: The TCP port to listen on.
    """

    host: str
    port: int


def main(argv: Sequence[str] | None = None) -> int:
    """Run the `ai-service` command.

    Args:
        argv: The arguments after the program name; the process arguments when None.

    Returns:
        The exit status: 0 when the server stopped, 2 for missing or invalid settings.
    """
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    events = build_event_recorder()
    try:
        settings = load_settings(events)
    except SettingsInvalidError:
        return EXIT_SETTINGS_INVALID
    app = create_app(settings, events, SystemClock(), NoReleaseSource())
    uvicorn.run(
        app,
        host=arguments.host,
        port=arguments.port,
        log_config=None,
        access_log=False,
        server_header=False,
    )
    return EXIT_SUCCESS


def build_event_recorder() -> EventRecorder:
    """Send every log record of the process to standard output as JSON lines (LOG-02).

    Returns:
        The event recorder of the process.
    """
    return StandardLibraryEventRecorder(
        configure_logging(sys.stdout, Redactor(GENERIC_REDACTION_PATTERNS))
    )


def parse_arguments(argv: Sequence[str]) -> ServeArguments:
    """Parse the command line.

    Args:
        argv: The arguments after the program name.

    Returns:
        The arguments of `serve`.
    """
    parser = argparse.ArgumentParser(prog="ai-service", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser(SERVE_COMMAND, help="Run one ai-service replica.")
    serve.add_argument("--host", required=True, help="The interface to listen on.")
    serve.add_argument("--port", required=True, type=int, help="The TCP port to listen on.")
    namespace = parser.parse_args(argv)
    return ServeArguments(host=str(namespace.host), port=int(namespace.port))
