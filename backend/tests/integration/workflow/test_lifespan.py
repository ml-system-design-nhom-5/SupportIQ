"""The lifespan of a replica with its default background work, the claim loop (ARCH-41, PY-34).

`create_app` runs the claim loop unless a test asks for none. Startup starts the loop, so a job
queued while no replica ran is claimed without a request. Shutdown, also after an error of the
server, stops the loop, cancels a running job, which its lease then recovers, and closes the
ai-service client (backend ticket workflow design, Suggestions and the job queue, item 8). The
lifespan awaits the loop, so a loop that does not stop makes the shutdown hang, and the bound of
each test fails it instead.

The ai-service of these tests is an in-memory transport that never answers, so no socket opens
and a job stays in the middle of its call until the shutdown. The waits of the clock end only
when they are cancelled, so only a wake-up or a stop ends a poll wait, the time never moves,
and no lease expires during a test (TEST-14).
"""

import asyncio
from dataclasses import dataclass, field
from http import HTTPStatus

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.composition_root import create_app
from supportiq_backend.platform import MILLISECONDS_PER_SECOND, EventName
from supportiq_backend.suggestions import SuggestionId
from tests.integration.ai_service_doubles import FakeAiService
from tests.integration.application import build_settings, running_app
from tests.integration.builders import DatabaseBuilder
from tests.integration.claim_loop_doubles import SignallingEventRecorder, WakeUpOnlyClock
from tests.integration.database import WorkerDatabase
from tests.integration.workflow.workflow_rows import (
    load_job_state,
    load_part_statuses,
    new_suggestion,
)
from tests.unit.platform.fakes import RecordingEventRecorder

pytestmark = pytest.mark.anyio

# The longest that startup, a test, and the shutdown may take before the test fails.
BOUND_MS = 10_000
FIRST_ATTEMPT = 1


class ServerStoppedError(Exception):
    """The error with which a test stops its server, as a crash of the server would."""


@dataclass(slots=True)
class SilentAnswer:
    """The answer of an ai-service that never answers.

    Attributes:
        called: Set when the first call arrives.
        answered: Never set by these tests, so every call waits until it is cancelled.
    """

    called: asyncio.Event = field(default_factory=asyncio.Event)
    answered: asyncio.Event = field(default_factory=asyncio.Event)

    async def __call__(self, request: httpx.Request) -> httpx.Response:
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


@dataclass(frozen=True, slots=True)
class SilentAiService:
    """An in-memory ai-service that never answers.

    Attributes:
        answer: Knows when the first call arrived.
        transport: The transport of the ai-service client of the replica.
    """

    answer: SilentAnswer
    transport: FakeAiService


@pytest.fixture
def ai_service() -> SilentAiService:
    """Give the replica of the test an ai-service that never answers."""
    answer = SilentAnswer()
    return SilentAiService(answer, FakeAiService(answer))


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
    app = create_app(
        build_settings(worker_database),
        RecordingEventRecorder(),
        WakeUpOnlyClock(),
        ai_service_transport=ai_service.transport,
    )
    async with bounded(), running_app(app):
        await ai_service.answer.called.wait()
    return suggestion_id


async def test_startup_starts_the_claim_loop_which_claims_a_job_queued_before(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    ai_service: SilentAiService,
) -> None:
    suggestion_id = await new_suggestion(app_engine, builder)
    recorded = RecordingEventRecorder()
    events = SignallingEventRecorder(recorded)
    app = create_app(
        build_settings(worker_database),
        events,
        WakeUpOnlyClock(),
        ai_service_transport=ai_service.transport,
    )

    async with bounded(), running_app(app):
        await events.wait_for(EventName.SUGGESTION_JOB_CLAIMED)

    (claimed,) = recorded.of(EventName.SUGGESTION_JOB_CLAIMED)
    assert claimed.attributes["suggestion_id"] == suggestion_id
    assert claimed.attributes["attempt_number"] == FIRST_ATTEMPT


async def test_shutdown_ends_the_wait_of_an_idle_claim_loop_and_closes_the_ai_service_client(
    worker_database: WorkerDatabase, ai_service: SilentAiService
) -> None:
    clock = WakeUpOnlyClock()
    app = create_app(
        build_settings(worker_database),
        RecordingEventRecorder(),
        clock,
        ai_service_transport=ai_service.transport,
    )

    async with bounded(), running_app(app):
        await clock.is_waiting.wait()

    assert ai_service.transport.is_closed


async def test_an_error_of_the_server_still_stops_the_claim_loop_and_releases_the_resources(
    worker_database: WorkerDatabase, ai_service: SilentAiService
) -> None:
    clock = WakeUpOnlyClock()
    events = RecordingEventRecorder()
    app = create_app(
        build_settings(worker_database), events, clock, ai_service_transport=ai_service.transport
    )

    # The bound fails the test if the claim loop is not stopped: the lifespan awaits it.
    with pytest.RaisesGroup(ServerStoppedError):
        async with bounded(), running_app(app):
            await clock.is_waiting.wait()
            raise ServerStoppedError

    assert ai_service.transport.is_closed
    assert EventName.SHUTDOWN_STARTED in events.names()


async def test_shutdown_in_the_middle_of_a_call_closes_the_ai_service_client(
    worker_database: WorkerDatabase,
    app_engine: AsyncEngine,
    builder: DatabaseBuilder,
    ai_service: SilentAiService,
) -> None:
    await shut_down_in_the_middle_of_a_call(worker_database, app_engine, builder, ai_service)

    assert ai_service.transport.is_closed


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
