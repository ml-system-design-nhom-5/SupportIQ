"""Adapter tests of stored texts that no enum of backend has, against PostgreSQL 17 (PY-20).

The stores of tickets, suggestions, and pseudonym maps read such a text as an unexpected failure
(ERR-05). A reason code is a value of a JSON array, so the owner inserts an unknown one; a
status or a type has a check constraint, which the test drops (`session_without_check`).
"""

from collections.abc import Awaitable, Callable
from datetime import timedelta
from uuid import UUID

import pytest
from sqlalchemy import insert, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from supportiq_backend.platform import UnexpectedFailureError
from supportiq_backend.platform.adapters.database import create_session_factory
from supportiq_backend.pseudonymization.adapters.pseudonym_map_store import (
    PostgresPseudonymMapStore,
)
from supportiq_backend.pseudonymization.adapters.tables import PseudonymMapEntryRow
from supportiq_backend.pseudonymization.domain import MapTicketId
from supportiq_backend.suggestions import SuggestionId, SuggestionTicketId, TicketForSuggestion
from supportiq_backend.suggestions.adapters.suggestion_store import (
    PostgresSuggestionJobStore,
    PostgresSuggestionStore,
)
from supportiq_backend.suggestions.adapters.tables import SuggestionJobRow
from supportiq_backend.tickets import ConsoleTicket, TicketId, TicketStatus
from supportiq_backend.tickets.adapters.console_store import (
    PostgresConsoleTicketStore,
    PostgresTicketLinks,
)
from supportiq_backend.tickets.adapters.escalation_store import PostgresEscalationStore
from supportiq_backend.tickets.adapters.proposal_store import PostgresReplyProposalStore
from supportiq_backend.tickets.adapters.reply_store import PostgresReplyStore
from supportiq_backend.tickets.adapters.tables import (
    EscalationRow,
    ReplyProposalRow,
    ReplyRow,
    TicketRow,
)
from tests.integration.builders import AccountSpec, DatabaseBuilder, SuggestionSpec
from tests.integration.database import WorkerDatabase
from tests.integration.stored_values import (
    DROP_HANDLING_MODE_CHECK,
    UNKNOWN_VALUE,
    session_without_check,
)
from tests.integration.workflow.workflow_rows import insert_ticket
from tests.unit.platform.fakes import FAKE_CLOCK_START

pytestmark = pytest.mark.anyio

DECIDED_AT = FAKE_CLOCK_START + timedelta(minutes=12)
BODY = "Your parcel left the warehouse today and should arrive on Friday."
DROP_JOB_STATE_CHECK = "ALTER TABLE suggestion_jobs DROP CONSTRAINT suggestion_jobs_state_check"
DROP_PSEUDONYM_TYPE_CHECK = (
    "ALTER TABLE pseudonym_map_entries DROP CONSTRAINT pseudonym_map_entries_pseudonym_type_check"
)
# A synthetic original value (TEST-18). The error of an unknown type must not hold it (SEC-37);
# a failing assertion that shows it would show only this synthetic text.
ORIGINAL_VALUE = "Lan Tran"
type ReadTicket = Callable[
    [AsyncSession, SuggestionTicketId],
    Awaitable[ConsoleTicket | TicketForSuggestion | tuple[ConsoleTicket, ...] | None],
]
# The size of the page of open tickets that the test loads.
PAGE_LIMIT = 10


async def load_console_ticket(
    session: AsyncSession, ticket_id: SuggestionTicketId
) -> ConsoleTicket | None:
    return await PostgresConsoleTicketStore(session).load_console_ticket(TicketId(ticket_id))


async def lock_console_ticket(
    session: AsyncSession, ticket_id: SuggestionTicketId
) -> ConsoleTicket | None:
    return await PostgresConsoleTicketStore(session).lock_console_ticket(TicketId(ticket_id))


async def load_open_tickets(
    session: AsyncSession, _: SuggestionTicketId
) -> tuple[ConsoleTicket, ...]:
    return await PostgresConsoleTicketStore(session).load_console_tickets(
        TicketStatus.OPEN, after=None, limit=PAGE_LIMIT
    )


async def lock_ticket(
    session: AsyncSession, ticket_id: SuggestionTicketId
) -> TicketForSuggestion | None:
    return await PostgresTicketLinks(session).lock_ticket(ticket_id)


async def insert_staff_and_suggestion(
    builder: DatabaseBuilder, ticket_id: str
) -> tuple[UUID, UUID]:
    """Insert a staff account and a suggestion of the ticket; return both IDs."""
    staff_id = await builder.account(AccountSpec("staff"))
    return staff_id, await builder.suggestion(ticket_id)


@pytest.mark.parametrize(
    "read_ticket",
    [load_console_ticket, lock_console_ticket, load_open_tickets, lock_ticket],
    ids=["console-store-load", "console-store-lock", "console-store-queue", "ticket-links"],
)
async def test_reading_a_ticket_of_an_unknown_handling_mode_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder, read_ticket: ReadTicket
) -> None:
    ticket_id = await insert_ticket(builder)
    unknown_mode = (
        update(TicketRow)
        .where(TicketRow.ticket_id == ticket_id)
        .values(handling_mode=UNKNOWN_VALUE)
    )

    async with session_without_check(
        worker_database, DROP_HANDLING_MODE_CHECK, unknown_mode
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await read_ticket(session, ticket_id)

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_escalation_of_an_unknown_staff_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    staff_id, suggestion_id = await insert_staff_and_suggestion(builder, ticket_id)
    await builder.execute(
        insert(EscalationRow).values(
            escalation_id=builder.next_uuid(),
            ticket_id=ticket_id,
            suggestion_id=suggestion_id,
            staff_reason_codes=[UNKNOWN_VALUE],
            escalated_by_account_id=staff_id,
            escalated_at=DECIDED_AT,
            note=None,
        )
    )

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresEscalationStore(session).load_escalation(TicketId(ticket_id))

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_proposal_of_an_unknown_staff_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    staff_id, suggestion_id = await insert_staff_and_suggestion(builder, ticket_id)
    await builder.execute(
        insert(ReplyProposalRow).values(
            proposal_id=builder.next_uuid(),
            ticket_id=ticket_id,
            basis="rejected_ai_draft",
            suggestion_id=suggestion_id,
            acknowledged_warning_ids=[],
            staff_reason_codes=[UNKNOWN_VALUE],
            proposed_by_account_id=staff_id,
            created_at=DECIDED_AT,
            body=BODY,
            note=None,
        )
    )

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresReplyProposalStore(session).load_proposal(TicketId(ticket_id))

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_reply_of_an_unknown_staff_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    staff_id, suggestion_id = await insert_staff_and_suggestion(builder, ticket_id)
    await builder.execute(
        insert(ReplyRow).values(
            reply_id=builder.next_uuid(),
            ticket_id=ticket_id,
            basis="rejected_ai_draft",
            suggestion_id=suggestion_id,
            acknowledged_warning_ids=[],
            staff_reason_codes=[UNKNOWN_VALUE],
            sent_by_account_id=staff_id,
            sent_at=DECIDED_AT,
            body=BODY,
            note=None,
        )
    )

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresReplyStore(session).load_reply(TicketId(ticket_id))

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_suggestion_of_an_unknown_ai_reason_code_is_an_unexpected_failure(
    app_engine: AsyncEngine, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    unavailable = SuggestionSpec("unavailable", UNKNOWN_VALUE, "done")
    suggestion_id = SuggestionId(str(await builder.suggestion(ticket_id, unavailable)))

    async with create_session_factory(app_engine)() as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresSuggestionStore(session).load_suggestion(suggestion_id)

    assert isinstance(caught.value.__cause__, ValueError)


async def test_lock_job_of_an_unknown_job_state_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    suggestion_id = await builder.suggestion(await insert_ticket(builder))
    unknown_state = (
        update(SuggestionJobRow)
        .where(SuggestionJobRow.suggestion_id == suggestion_id)
        .values(state=UNKNOWN_VALUE)
    )

    async with session_without_check(
        worker_database, DROP_JOB_STATE_CHECK, unknown_state
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresSuggestionJobStore(session).lock_job(SuggestionId(str(suggestion_id)))

    assert isinstance(caught.value.__cause__, ValueError)


async def test_load_entries_of_an_unknown_pseudonym_type_is_an_unexpected_failure(
    worker_database: WorkerDatabase, builder: DatabaseBuilder
) -> None:
    ticket_id = await insert_ticket(builder)
    unknown_type = insert(PseudonymMapEntryRow).values(
        ticket_id=ticket_id,
        pseudonym="[NAME_1]",
        pseudonym_type=UNKNOWN_VALUE,
        original_value=ORIGINAL_VALUE,
        created_at=DECIDED_AT,
    )

    async with session_without_check(
        worker_database, DROP_PSEUDONYM_TYPE_CHECK, unknown_type
    ) as session:
        with pytest.raises(UnexpectedFailureError) as caught:
            await PostgresPseudonymMapStore(session).load_entries(MapTicketId(ticket_id))

    assert isinstance(caught.value.__cause__, ValueError)
    assert ORIGINAL_VALUE not in f"{caught.value!r} {caught.value.__cause__!r}"
