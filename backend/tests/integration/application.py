"""The wired backend application, run in the test process against the worker database."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from app.composition_root import BackgroundWork, create_app
from app.platform import EventRecorder
from app.platform.settings import DatabaseTls, Settings
from tests.integration.ai_service_doubles import FakeAiService, refuse_connection
from tests.integration.database import WorkerDatabase
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder
from tests.unit.platform.settings_builders import build_test_settings

ALLOWED_ORIGIN = "http://shop.test"
BASE_URL = "http://backend.test"
ORIGIN_HEADERS = {"Origin": ALLOWED_ORIGIN}


@dataclass(frozen=True, slots=True)
class RunningBackend:
    """The application under test, with what the tests observe of it.

    Attributes:
        client: An HTTP client whose requests go to the application.
        clock: The fake clock of the application.
        events: The events that the application recorded.
    """

    client: httpx.AsyncClient
    clock: FakeClock
    events: RecordingEventRecorder


def session_headers(token: str) -> dict[str, str]:
    """Return the headers of a request with a session cookie and an allowed `Origin`.

    Args:
        token: The raw session identifier.

    Returns:
        The headers.
    """
    return {"Cookie": f"supportiq_session={token}", **ORIGIN_HEADERS}


def build_settings(worker_database: WorkerDatabase, **overrides: object) -> Settings:
    """Build the settings of a replica that uses the worker database.

    Args:
        worker_database: The database of the worker.
        **overrides: Settings that replace the initial values of the design.

    Returns:
        The validated settings. The environment is not read.
    """
    values: dict[str, object] = {
        "database_url_app": worker_database.app_url,
        # The test cluster runs on the same host without TLS (README, TLS to the database).
        "database_tls": DatabaseTls.DISABLE,
        "allowed_origins": (ALLOWED_ORIGIN,),
        "session_cookie_secure": False,
        # The test client returns only once a stream ends, and the fake clock ends each wait
        # at once, so a stream of a pending part ends at this limit after one re-read.
        "suggestion_events_max_ms": 2_000,
    }
    return build_test_settings(**(values | overrides))


@asynccontextmanager
async def running_client(
    settings: Settings,
    events: EventRecorder,
    clock: FakeClock,
    *,
    ai_service: FakeAiService | None = None,
) -> AsyncGenerator[httpx.AsyncClient]:
    """Start the application with its lifespan and yield an HTTP client to it.

    Args:
        settings: The settings of the replica.
        events: Where the application records events.
        clock: The clock of the application.
        ai_service: The in-memory ai-service; by default one that refuses every connection.

    Yields:
        A client whose requests go to the application in the test process.
    """
    # No claim loop: no job runs behind the back of a test of the HTTP operations.
    app = create_app(
        settings,
        events,
        clock,
        background=BackgroundWork.NONE,
        ai_service_transport=FakeAiService(refuse_connection) if ai_service is None else ai_service,
    )
    async with running_app(app) as client:
        yield client


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
