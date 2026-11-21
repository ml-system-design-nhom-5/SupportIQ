"""The wired ai-service application, run in the test process with fakes for its ports."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.composition_root import ServicePorts, create_app
from app.platform.adapters.egress import (
    create_egress_client,
    packaged_egress_allow_list,
)
from app.platform.settings import Settings
from app.release import ReleaseSource
from app.retrieval import KbDocumentSource
from app.suggestions import SuggestionPipeline
from tests.unit.platform.fakes import (
    LLM_ENVIRONMENT,
    FakeClock,
    RecordingEventRecorder,
    RecordingNetwork,
)
from tests.unit.release.fakes import StaticReleaseSource
from tests.unit.retrieval.fakes import StaticKbDocuments
from tests.unit.suggestions.fakes import FakePipeline

BASE_URL = "http://ai-service.test"
SERVICE_TOKEN = "service-token-for-integration-tests"
SERVICE_TOKEN_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
# `create_app` never reads the release manifest: only the command checks it, before it creates
# the application. So a replica built from its ports takes a path that names no file.
UNCHECKED_RELEASE_MANIFEST_PATH = Path("release-manifest.json")


@dataclass(frozen=True, slots=True)
class RunningAiService:
    """The application under test, with what the tests observe of it.

    Attributes:
        client: An HTTP client whose requests go to the application.
        events: The events that the application recorded.
    """

    client: httpx.AsyncClient
    events: RecordingEventRecorder


def build_settings(release_manifest_path: Path = UNCHECKED_RELEASE_MANIFEST_PATH) -> Settings:
    """Build the settings of a replica for tests, without reading the environment.

    Args:
        release_manifest_path: The release manifest; one that names no file by default.

    Returns:
        The validated settings with the test service token.
    """
    return Settings.model_validate(
        {
            "service_token": SERVICE_TOKEN,
            "release_manifest_path": release_manifest_path,
            **{name.lower(): value for name, value in LLM_ENVIRONMENT.items()},
        }
    )


def build_ports(
    release_source: ReleaseSource | None = None,
    pipeline: SuggestionPipeline | None = None,
    kb_documents: KbDocumentSource | None = None,
) -> ServicePorts:
    """Build the ports of a replica for tests, with the examples of the contract by default.

    Args:
        release_source: The release source; the example release when None.
        pipeline: The pipeline; one that answers the contract's examples when None.
        kb_documents: The KB; one with the example document version when None.

    Returns:
        The ports.
    """
    return ServicePorts(
        release_source=StaticReleaseSource() if release_source is None else release_source,
        pipeline=FakePipeline() if pipeline is None else pipeline,
        kb_documents=StaticKbDocuments() if kb_documents is None else kb_documents,
    )


def build_app(ports: ServicePorts, events: RecordingEventRecorder) -> FastAPI:
    """Create the wired application for tests.

    Its egress client has the packaged allow-list and a recording network, so nothing it
    could send would connect.

    Args:
        ports: The ports of the replica.
        events: Where the application records events.

    Returns:
        The application.
    """
    egress_client = create_egress_client(packaged_egress_allow_list(), RecordingNetwork())
    return create_app(build_settings(), events, FakeClock(), ports, egress_client)


@asynccontextmanager
async def running_app(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    """Run the lifespan of an application and yield an HTTP client to it.

    Args:
        app: The application.

    Yields:
        A client whose requests go to the application in the test process.
    """
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            yield client


@asynccontextmanager
async def running_ai_service(
    release_source: ReleaseSource | None = None,
    pipeline: SuggestionPipeline | None = None,
    kb_documents: KbDocumentSource | None = None,
) -> AsyncGenerator[RunningAiService]:
    """Start the application with its lifespan and yield an HTTP client to it.

    Args:
        release_source: The release source; the example release when None.
        pipeline: The pipeline; one that answers the contract's examples when None.
        kb_documents: The KB; one with the example document version when None.

    Yields:
        The running application and its recorded events.
    """
    events = RecordingEventRecorder()
    app = build_app(build_ports(release_source, pipeline, kb_documents), events)
    async with running_app(app) as client:
        yield RunningAiService(client, events)
