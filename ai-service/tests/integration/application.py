"""The wired ai-service application, run in the test process with fakes for its ports."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx

from supportiq_ai_service.composition_root import create_app
from supportiq_ai_service.platform.settings import Settings
from supportiq_ai_service.release import ReleaseSource
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder
from tests.unit.release.fakes import StaticReleaseSource

BASE_URL = "http://ai-service.test"
SERVICE_TOKEN = "service-token-for-integration-tests"
SERVICE_TOKEN_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


@dataclass(frozen=True, slots=True)
class RunningAiService:
    """The application under test, with what the tests observe of it.

    Attributes:
        client: An HTTP client whose requests go to the application.
        events: The events that the application recorded.
    """

    client: httpx.AsyncClient
    events: RecordingEventRecorder


def build_settings() -> Settings:
    """Build the settings of a replica for tests, without reading the environment.

    Returns:
        The validated settings with the test service token.
    """
    return Settings.model_validate({"service_token": SERVICE_TOKEN})


@asynccontextmanager
async def running_ai_service(
    release_source: ReleaseSource | None = None,
) -> AsyncGenerator[RunningAiService]:
    """Start the application with its lifespan and yield an HTTP client to it.

    Args:
        release_source: The release source; the example release when None.

    Yields:
        The running application and its recorded events.
    """
    events = RecordingEventRecorder()
    source = StaticReleaseSource() if release_source is None else release_source
    app = create_app(build_settings(), events, FakeClock(), source)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url=BASE_URL) as client:
            yield RunningAiService(client, events)
