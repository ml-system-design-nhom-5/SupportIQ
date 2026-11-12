"""The wired backend application, run in the test process against the worker database."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI

from supportiq_backend.composition_root import BackgroundWork, create_app
from supportiq_backend.platform import EventRecorder
from supportiq_backend.platform.settings import Settings
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
        "allowed_origins": (ALLOWED_ORIGIN,),
        "session_cookie_secure": False,
    }
    return build_test_settings(**(values | overrides))


@asynccontextmanager
async def running_client(
    settings: Settings, events: EventRecorder, clock: FakeClock
) -> AsyncGenerator[httpx.AsyncClient]:
    """Start the application with its lifespan and yield an HTTP client to it.

    Args:
        settings: The settings of the replica.
        events: Where the application records events.
        clock: The clock of the application.

    Yields:
        A client whose requests go to the application in the test process.
    """
    # No claim loop: no job runs behind the back of a test of the HTTP operations.
    app = create_app(settings, events, clock, background=BackgroundWork.NONE)
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
