"""The `ai-service` command: run one replica.

It reads the settings first and stops with status 2, after logging `settings.invalid` with
the names of the bad settings, when one is missing or invalid (ARCH-34). It then reads the
packaged egress allow-list, and stops the same way, after logging `egress_allow_list.invalid`
with the file name, when the file is missing or invalid (SEC-40). It then checks the release
manifest and every file it names, and stops the same way, after logging `release.invalid`
with the reason, when one is missing or does not match (DATA-56). From the allow-list it
creates the one HTTP client that leaves the system, before the server starts.
"""

import argparse
import sys
from collections.abc import Sequence
from dataclasses import dataclass

import uvicorn
from fastapi import FastAPI

from supportiq_ai_service.composition_root.settings_loading import (
    SettingsInvalidError,
    load_settings,
)
from supportiq_ai_service.composition_root.web_application import ServicePorts, create_app
from supportiq_ai_service.platform import EventAttributeValue, EventName, EventRecorder
from supportiq_ai_service.platform.adapters.egress import (
    EgressAllowListInvalidError,
    create_egress_client,
    packaged_egress_allow_list,
)
from supportiq_ai_service.platform.adapters.logging_setup import (
    GENERIC_REDACTION_PATTERNS,
    Redactor,
    StandardLibraryEventRecorder,
    configure_logging,
)
from supportiq_ai_service.platform.adapters.system_clock import SystemClock
from supportiq_ai_service.platform.settings import Settings
from supportiq_ai_service.release.manifest import ReleaseInvalidError, verify_release
from supportiq_ai_service.retrieval.adapters.no_kb_documents import NoKbDocuments
from supportiq_ai_service.suggestions.adapters import UnavailablePipeline

EXIT_SUCCESS = 0
EXIT_CONFIGURATION_INVALID = 2
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
        The exit status: 0 when the server stopped, 2 for missing or invalid settings, a
        missing or invalid egress allow-list, or a release that fails its check.
    """
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    events = build_event_recorder()
    try:
        settings = load_settings(events)
    except SettingsInvalidError:
        return EXIT_CONFIGURATION_INVALID
    try:
        app = build_application(settings, events)
    except EgressAllowListInvalidError as error:
        events.record(EventName.EGRESS_ALLOW_LIST_INVALID, file_name=error.file_name)
        return EXIT_CONFIGURATION_INVALID
    except ReleaseInvalidError as error:
        events.record(EventName.RELEASE_INVALID, **release_refusal_attributes(error))
        return EXIT_CONFIGURATION_INVALID
    uvicorn.run(
        app,
        host=arguments.host,
        port=arguments.port,
        log_config=None,
        access_log=False,
        server_header=False,
    )
    return EXIT_SUCCESS


def build_application(settings: Settings, events: EventRecorder) -> FastAPI:
    """Wire one replica: its adapters, its ports, and its application (ARCH-21).

    It checks the release before it creates anything, and it creates the HTTP client of the
    egress allow-list here, once, and nowhere else. Creating the client does no I/O, and the
    lifespan of the application closes it at shutdown (ARCH-24, SEC-40).

    Args:
        settings: The validated settings.
        events: Where events are recorded.

    Returns:
        The application, ready for an ASGI server.

    Raises:
        EgressAllowListInvalidError: The packaged egress allow-list is missing or invalid.
        ReleaseInvalidError: The release manifest, or a file it names, fails its check.
    """
    allow_list = packaged_egress_allow_list()
    release_source = verify_release(settings.release_manifest_path)
    events.record(EventName.RELEASE_LOADED, release_id=release_source.manifest.release_id)
    egress_client = create_egress_client(allow_list)
    ports = ServicePorts(
        release_source=release_source,
        pipeline=UnavailablePipeline(),
        kb_documents=NoKbDocuments(),
    )
    return create_app(settings, events, SystemClock(), ports, egress_client)


def release_refusal_attributes(error: ReleaseInvalidError) -> dict[str, EventAttributeValue]:
    """Return the attributes of `release.invalid`: the reason, and the asset and file if any.

    Args:
        error: Why the release was refused.

    Returns:
        The attributes, without the content of any file.
    """
    attributes: dict[str, EventAttributeValue] = {"reason": error.reason.value}
    if error.asset is not None:
        attributes["asset"] = error.asset
    if error.file_path is not None:
        attributes["file_path"] = error.file_path
    return attributes


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
