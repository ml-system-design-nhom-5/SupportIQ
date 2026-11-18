"""Guardrail: a name that backend does not hold never reaches ai-service (TEST-26, FR-09, NFR-06).

A replica runs with its claim loop and every detector of ADR-0010, the named-entity model
included. The message names a third person, whom no known value covers, and a product of the
catalog that the model reads as a person. The job sends ai-service a pseudonym for the person
and the product name as written (ADR-0010, Detection, step 4). The test waits for the event of
the job, and the bound fails it instead of letting it hang (TEST-14).
"""

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from supportiq_backend.composition_root import BackgroundWork, create_app
from supportiq_backend.platform import MILLISECONDS_PER_SECOND, EventName
from tests.integration.ai_service_doubles import FakeAiService, serve_examples
from tests.integration.application import build_settings, running_app
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.claim_loop_doubles import SignallingEventRecorder, WakeUpOnlyClock
from tests.integration.database import WorkerDatabase
from tests.integration.workflow.workflow_rows import (
    insert_ticket,
    start_suggestion,
    ticket_created,
)
from tests.unit.platform.fakes import RecordingEventRecorder

pytestmark = pytest.mark.anyio

PRODUCT = "Jordan Runner"
THIRD_PERSON = ("Anna Kowalski", "Kowalski")
MESSAGE = f"Please send the {PRODUCT} shoes to my sister {THIRD_PERSON[0]}."
BOUND_MS = 10_000


async def test_a_third_person_reaches_ai_service_as_a_pseudonym_and_a_product_as_written(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    await builder.product(name=PRODUCT)
    ticket_id = await insert_ticket(builder, TicketSpec(message=MESSAGE))
    await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    events = SignallingEventRecorder(RecordingEventRecorder())
    ai_service = FakeAiService(serve_examples)
    app = create_app(
        build_settings(worker_database),
        events,
        WakeUpOnlyClock(events),
        background=BackgroundWork.SUGGESTION_JOBS,
        ai_service_transport=ai_service,
    )

    async with asyncio.timeout(BOUND_MS / MILLISECONDS_PER_SECOND), running_app(app):
        await events.wait_for(EventName.SUGGESTION_COMPLETED)

    sent = ai_service.sent_text()
    assert [value for value in THIRD_PERSON if value in sent] == []
    assert "[NAME_" in sent
    assert PRODUCT in sent
