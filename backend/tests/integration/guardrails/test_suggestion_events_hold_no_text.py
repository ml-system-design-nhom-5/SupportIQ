"""Guardrail: the suggestion progress stream holds Internal values only (TEST-26, SEC-01).

Each event carries the suggestion ID and the two part statuses, never message text or AI text:
the console reads any text with `getConsoleTicket`, which restores pseudonyms and checks the
role (ADR-0022, statement 2). The scenario stores a draft with its text and staff note, keeps
the analysis pending so the stream opens, and follows the stream until its time limit.
"""

import json

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from app.suggestions import DraftReady, SuggestionTicketId, build_draft_completion
from tests.integration.application import build_settings, running_client
from tests.integration.builders import DatabaseBuilder, TicketSpec
from tests.integration.database import WorkerDatabase
from tests.integration.tickets.console_requests import sign_in_as_support
from tests.integration.workflow.workflow_rows import (
    complete_parts,
    insert_ticket,
    received_draft_example,
    start_suggestion,
    ticket_created,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START, FakeClock, RecordingEventRecorder

pytestmark = pytest.mark.anyio

MESSAGE = "Marker-7Q4 asks where the parcel to 12 Example Street is."
EVENT_FIELDS = {"suggestion_id", "analysis_status", "draft_status"}


async def test_every_event_holds_only_the_suggestion_id_and_the_two_statuses(
    worker_database: WorkerDatabase, app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = SuggestionTicketId(await insert_ticket(builder, TicketSpec(message=MESSAGE)))
    suggestion_id = await start_suggestion(app_engine, builder, ticket_created(ticket_id))
    received = received_draft_example("draft-ready")
    await complete_parts(
        app_engine, suggestion_id, build_draft_completion(received, FAKE_CLOCK_START)
    )
    outcome = received.outcome
    assert isinstance(outcome, DraftReady)
    assert outcome.details.staff_note is not None
    ai_texts = [outcome.details.staff_note, *(segment.text for segment in outcome.draft.segments)]
    headers = (await sign_in_as_support(builder)).headers
    settings = build_settings(worker_database, suggestion_events_max_ms=1_000)

    async with running_client(settings, RecordingEventRecorder(), FakeClock()) as client:
        response = await client.get(
            f"/v1/console/tickets/{ticket_id}/suggestion-events", headers=headers
        )

    data_lines = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert data_lines
    assert all(set(json.loads(line.removeprefix("data: "))) == EVENT_FIELDS for line in data_lines)
    assert "Marker-7Q4" not in response.text
    assert all(text not in response.text for text in ai_texts)
