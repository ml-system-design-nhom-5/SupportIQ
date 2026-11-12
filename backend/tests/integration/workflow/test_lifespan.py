"""The lifespan of a replica with its default background work, the claim loop (ARCH-41, PY-34).

`create_app` runs the claim loop unless a test asks for none. Startup starts the loop, so a job
queued while no replica ran is claimed without a request. Shutdown stops the loop, cancels a
running job, which its lease then recovers, and closes the ai-service client (backend ticket
workflow design, Suggestions and the job queue, item 8). The lifespan awaits the loop, so a
loop that does not stop makes the shutdown hang, and the bound of each test fails it instead.

The ai-service of these tests is an in-memory transport that never answers, so no socket opens
and a job stays in the middle of its call until the shutdown. The waits of the clock end only
when they are cancelled, so only a wake-up or a stop ends a poll wait, the time never moves,
and no lease expires during a test (TEST-14).
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from http import HTTPStatus

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.composition_root import create_app
from supportiq_backend.platform import MILLISECONDS_PER_SECOND, EventAttributeValue, EventName
from supportiq_backend.suggestions import SuggestionId
from supportiq_backend.suggestions.adapters.ai_service_client import create_ai_service_client
from tests.integration.application import build_settings, running_app
from tests.integration.builders import DatabaseBuilder
from tests.integration.database import WorkerDatabase
from tests.integration.workflow.workflow_rows import (
    load_job_state,
    load_part_statuses,
    new_suggestion,
)
from tests.unit.platform.fakes import FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

# The longest that startup, a test, and the shutdown may take before the test fails.
BOUND_MS = 10_000
# The factory of the ai-service client that the wiring of suggestions calls.
AI_SERVICE_CLIENT_FACTORY = (
    "supportiq_backend.composition_root.suggestions_wiring.create_ai_service_client"
)
FIRST_ATTEMPT = 1


@dataclass(slots=True)
class SilentAiService:
    """An in-memory ai-service that never answers, with the client of each replica on it.

    Attributes:
        called: Set when the first call arrives.
        clients: The ai-service client of each replica, in the order they were created.
        answered: Never set by these tests, so every call waits until it is cancelled.
    """

    called: asyncio.Event = field(default_factory=asyncio.Event)
    clients: list[httpx.AsyncClient] = field(default_factory=list[httpx.AsyncClient])
    answered: asyncio.Event = field(default_factory=asyncio.Event)

    async def answer(self, request: httpx.Request) -> httpx.Response:
        """Note the call and wait until it is cancelled.

        Args:
            request: The call.

        Returns:
            A `503`, only if a test ever sets `answered`.
        """
        del request
        self.called.set()
        await self.answered.wait()
        return httpx.Response(HTTPStatus.SERVICE_UNAVAILABLE)

    def create_client(self, base_url: str, service_token: str) -> httpx.AsyncClient:
        """Create the ai-service client of a replica on this transport, and keep it.

        Args:
            base_url: `ai_service_base_url`.
            service_token: The service token.

        Returns:
            The client, as `create_ai_service_client` creates it.
        """
        client = create_ai_service_client(
            base_url, service_token, transport=httpx.MockTransport(self.answer)
        )
        self.clients.append(client)
        return client


class SignallingEventRecorder:
    """Keep every event as `RecordingEventRecorder` does, and let a test wait for one."""

    def __init__(self) -> None:
        """Start with no event."""
        self.recorded = RecordingEventRecorder()
        self._signals: defaultdict[EventName, asyncio.Event] = defaultdict(asyncio.Event)

    def record(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Keep the event and wake the tests that wait for it.

        Args:
            event: The event.
            **attributes: Its attributes.
        """
        self.recorded.record(event, **attributes)
        self._signals[event].set()

    def record_handled_input(self, event: EventName, /, **attributes: EventAttributeValue) -> None:
        """Keep the event caused by handled input and wake the tests that wait for it.

        Args:
            event: The event.
            **attributes: Its attributes.
        """
        self.recorded.record_handled_input(event, **attributes)
        self._signals[event].set()

    async def wait_for(self, event: EventName) -> None:
        """Return once the event was recorded.

        Args:
            event: The event.
        """
        await self._signals[event].wait()


class WakeUpOnlyClock(FakeClock):
    """A fake clock whose waits end only when cancelled, so only a wake-up ends a poll wait."""

    def __init__(self) -> None:
        """Start the clock at the fake start time, with no wait yet."""
        super().__init__()
        self.is_waiting = asyncio.Event()

    async def sleep(self, duration_ms: int) -> None:
        """Record the wait, and wait until it is cancelled; the time does not move.

        Args:
            duration_ms: The duration of the wait, in milliseconds.
        """
        self.sleeps_ms.append(duration_ms)
        self.is_waiting.set()
        await asyncio.Event().wait()


@pytest.fixture
def ai_service(monkeypatch: pytest.MonkeyPatch) -> SilentAiService:
    """Give each replica of the test the silent ai-service.

    Args:
        monkeypatch: Replaces the factory of the ai-service client for the test.

    Returns:
        The silent ai-service.
    """
    service = SilentAiService()
    monkeypatch.setattr(AI_SERVICE_CLIENT_FACTORY, service.create_client)
    return service


def bounded() -> asyncio.Timeout:
    return asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND)


async def shut_down_in_the_middle_of_a_call(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    ai_service: SilentAiService,
) -> SuggestionId:
    """Queue a job, start a replica, and stop it while the job waits for ai-service.

    Returns:
        The suggestion of the job.
    """
    suggestion_id = await new_suggestion(app_engine, builder)
    app = create_app(build_settings(worker_database), RecordingEventRecorder(), WakeUpOnlyClock())
    async with bounded(), running_app(app):
        await ai_service.called.wait()
    return suggestion_id


@pytest.mark.usefixtures("ai_service")
async def test_startup_starts_the_claim_loop_which_claims_a_job_queued_before(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    events = SignallingEventRecorder()
    app = create_app(build_settings(worker_database), events, WakeUpOnlyClock())

    async with bounded(), running_app(app):
        await events.wait_for(EventName.SUGGESTION_JOB_CLAIMED)

    (claimed,) = events.recorded.of(EventName.SUGGESTION_JOB_CLAIMED)
    assert claimed.attributes["suggestion_id"] == suggestion_id
    assert claimed.attributes["attempt_number"] == FIRST_ATTEMPT


async def test_shutdown_ends_the_wait_of_an_idle_claim_loop_and_closes_the_ai_service_client(
    worker_database: WorkerDatabase, ai_service: SilentAiService
) -> None:
    clock = WakeUpOnlyClock()
    app = create_app(build_settings(worker_database), RecordingEventRecorder(), clock)

    async with bounded(), running_app(app):
        await clock.is_waiting.wait()

    (client,) = ai_service.clients
    assert client.is_closed


async def test_shutdown_in_the_middle_of_a_call_closes_the_ai_service_client(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    ai_service: SilentAiService,
) -> None:
    await shut_down_in_the_middle_of_a_call(worker_database, app_engine, builder, ai_service)

    (client,) = ai_service.clients
    assert client.is_closed


async def test_a_job_stopped_by_the_shutdown_stays_running_for_its_lease(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    ai_service: SilentAiService,
) -> None:
    suggestion_id = await shut_down_in_the_middle_of_a_call(
        worker_database, app_engine, builder, ai_service
    )

    job_state = await load_job_state(builder, suggestion_id)
    part_statuses = await load_part_statuses(builder, suggestion_id)
    assert job_state == {"state": "running", "attempt_number": FIRST_ATTEMPT}
    assert part_statuses == {"analysis": "pending", "draft": "pending"}
