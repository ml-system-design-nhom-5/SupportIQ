"""Refusals and failures of `CreateSuggestion` with fakes of every port (SEC-41, ERR-15).

A refused or failed request starts no suggestion, commits nothing, and wakes no claim loop, so
no job runs for a suggestion that was never stored (backend ticket workflow design).
"""

from uuid import UUID

import pytest

from supportiq_backend.accounts import (
    AccountId,
    CustomerId,
    CustomerPrincipal,
    ForbiddenRoleError,
    InternalPrincipal,
    InternalRole,
    Principal,
    SupportPrincipal,
    SupportRole,
)
from supportiq_backend.idempotency import IdempotencyKey, IdempotencyKeyReusedError
from supportiq_backend.platform import DatabaseUnavailableError, EventName, ResourceNotFoundError
from supportiq_backend.suggestions import (
    AiReasonCode,
    IntentLabel,
    SuggestionTicketId,
    TicketForSuggestion,
)
from tests.unit.suggestions.builders import (
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    TICKET_ID,
    build_failed_suggestion,
    build_ready_suggestion,
)
from tests.unit.suggestions.create_suggestion_fakes import build_create_suggestion_harness

pytestmark = pytest.mark.anyio

OTHER_TICKET_ID = SuggestionTicketId("TCK-1043")
UNKNOWN_TICKET_ID = SuggestionTicketId("TCK-9999")
KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000654"))
SUPPORT = SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole.STAFF)
CUSTOMER = CustomerPrincipal(
    AccountId("00000000-0000-4000-8000-0000000000cc"),
    CustomerId("00000000-0000-4000-8000-0000000000c1"),
)
ADMIN = InternalPrincipal(AccountId("00000000-0000-4000-8000-0000000000ad"), InternalRole.ADMIN)
CHOSEN_INTENT = IntentLabel.REQUEST_REFUND
OPEN_TICKET = TicketForSuggestion(SUGGESTION_ID, True, True, "open")
OPEN_TICKETS = {TICKET_ID: OPEN_TICKET, OTHER_TICKET_ID: OPEN_TICKET}
FAILED = build_failed_suggestion(AiReasonCode.AI_SERVICE_UNAVAILABLE)


@pytest.mark.parametrize(("principal", "role"), [(CUSTOMER, "customer"), (ADMIN, "admin")])
async def test_customers_and_admins_may_not_create_a_suggestion(
    principal: Principal, role: str
) -> None:
    harness = build_create_suggestion_harness(OPEN_TICKETS, FAILED)

    with pytest.raises(ForbiddenRoleError):
        harness.create.authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "createSuggestion",
    }


@pytest.mark.parametrize("role", [InternalRole.STAFF, InternalRole.MANAGER])
async def test_staff_and_managers_may_create_a_suggestion(role: InternalRole) -> None:
    harness = build_create_suggestion_harness(OPEN_TICKETS, FAILED)

    support = harness.create.authorize(InternalPrincipal(STAFF_ACCOUNT_ID, role))

    assert support == SupportPrincipal(STAFF_ACCOUNT_ID, SupportRole(role.value))


async def test_an_unknown_ticket_starts_nothing_and_commits_nothing() -> None:
    harness = build_create_suggestion_harness(OPEN_TICKETS, FAILED)

    with pytest.raises(ResourceNotFoundError):
        await harness.create.execute(SUPPORT, UNKNOWN_TICKET_ID, None, KEY)

    assert harness.queue.notifications == []
    assert harness.transactions.commit_count == 0


@pytest.mark.parametrize(
    ("ticket_id", "intent_override"),
    [(TICKET_ID, CHOSEN_INTENT), (OTHER_TICKET_ID, None)],
    ids=["another-body", "another-ticket"],
)
async def test_a_key_reused_with_another_request_starts_no_second_suggestion(
    ticket_id: SuggestionTicketId, intent_override: IntentLabel | None
) -> None:
    harness = build_create_suggestion_harness(OPEN_TICKETS, FAILED)
    await harness.create.execute(SUPPORT, TICKET_ID, None, KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await harness.create.execute(SUPPORT, ticket_id, intent_override, KEY)

    assert len(harness.queue.notifications) == 1
    assert harness.transactions.commit_count == 1


async def test_an_unavailable_database_starts_nothing_and_records_no_override() -> None:
    harness = build_create_suggestion_harness(OPEN_TICKETS, build_ready_suggestion())
    harness.suggestions.failure = DatabaseUnavailableError()

    with pytest.raises(DatabaseUnavailableError):
        await harness.create.execute(SUPPORT, TICKET_ID, CHOSEN_INTENT, KEY)

    assert harness.queue.notifications == []
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.INTENT_OVERRIDDEN) == ()


async def test_a_failed_commit_wakes_no_claim_loop() -> None:
    harness = build_create_suggestion_harness(
        OPEN_TICKETS, build_ready_suggestion(), commit_failure=DatabaseUnavailableError()
    )

    with pytest.raises(DatabaseUnavailableError):
        await harness.create.execute(SUPPORT, TICKET_ID, CHOSEN_INTENT, KEY)

    assert harness.queue.notifications == []
    assert harness.events.of(EventName.INTENT_OVERRIDDEN) == ()
