"""Tests of `createReplyProposal` with fakes of every port (backend ticket workflow design).

Staff propose a reply for a manager to send, also on a ticket that requires authority; the
proposal never reaches the customer (FR-04, FR-06). The checks follow the check order of the
contract, and a body with a placeholder is refused (SEC-38).
"""

import json
from dataclasses import replace
from uuid import UUID

import pytest

from app.accounts import ForbiddenRoleError, Principal
from app.audit import AuditEventType
from app.idempotency import IdempotencyKey, IdempotencyKeyReusedError
from app.platform import EventName
from app.suggestions import (
    InvalidTicketStateError,
    NoDraftStatus,
    SuggestionId,
    SuggestionPendingError,
    SuggestionSupersededError,
)
from app.tickets import (
    AiDraftReply,
    HandlingMode,
    NoAiDraftReply,
    NoteRequiredError,
    PlaceholderInBodyError,
    RejectedAiDraftReply,
    ReplyBasisInvalidError,
    ReplyProposal,
    StaffReasonCode,
    TicketId,
    TicketNotFoundError,
    TicketStatus,
    WarningsNotAcknowledgedError,
)
from tests.unit.platform.fakes import FAKE_CLOCK_START
from tests.unit.suggestions.builders import (
    STAFF_ACCOUNT_ID,
    SUGGESTION_ID,
    build_analysis,
    build_draft_ready,
    build_no_draft,
    build_ready_suggestion,
    build_suggestion,
)
from tests.unit.suggestions.fakes import FakeRestorer
from tests.unit.tickets.console_fakes import (
    ADMIN,
    CUSTOMER,
    KEY,
    SIGNED_IN_MANAGER,
    SIGNED_IN_STAFF,
    STAFF,
    TICKET_ID,
    ConsoleHarness,
    build_console_harness,
    build_console_ticket,
    build_propose,
    with_suggestion,
    with_ticking_clock,
)
from tests.unit.tickets.fakes import MANAGER_ACCOUNT_ID

pytestmark = pytest.mark.anyio

DRAFT_TEXT = "Hello [NAME_1], your refund is under review."
RESTORED_DRAFT_TEXT = "Hello Lan Tran, your refund is under review."
RESTORER = FakeRestorer({"[NAME_1]": "Lan Tran"})
OWN_TEXT = "A manager will confirm your refund."
NOTE = "The customer asked for the manager by name."
OTHER_KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000124"))
OTHER_SUGGESTION_ID = SuggestionId("00000000-0000-4000-8000-000000000002")
WARNING_ID = "w1"
UNKNOWN_TICKET_ID = TicketId("TCK-9999")
NOT_OPEN = [TicketStatus.AWAITING_APPROVAL, TicketStatus.ESCALATED, TicketStatus.CLOSED]
REFUSED_ROLES = [(CUSTOMER, "customer"), (ADMIN, "admin")]


def ai_draft_proposal(body: str = RESTORED_DRAFT_TEXT, **changes: object) -> AiDraftReply:
    proposal = AiDraftReply(body, SUGGESTION_ID, frozenset(), (), None)
    return replace(proposal, **changes)


def ready_harness(*, is_authority_required: bool = False) -> ConsoleHarness:
    return with_suggestion(
        build_console_harness(
            build_console_ticket(is_authority_required=is_authority_required), restorer=RESTORER
        ),
        build_ready_suggestion(build_draft_ready((0, DRAFT_TEXT))),
    )


def stored_proposal(harness: ConsoleHarness) -> ReplyProposal:
    return harness.proposals.proposals[TICKET_ID]


def assert_nothing_proposed(harness: ConsoleHarness) -> None:
    assert harness.proposals.proposals == {}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.OPEN
    assert harness.transactions.commit_count == 0
    assert harness.events.of(EventName.REPLY_PROPOSAL_SUBMITTED) == ()


async def test_staff_propose_the_draft_of_a_ticket_that_requires_authority() -> None:
    harness = ready_harness(is_authority_required=True)

    response = await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    proposal = stored_proposal(harness)
    assert (proposal.ticket_id, proposal.proposed_by, proposal.created_at) == (
        TICKET_ID,
        STAFF_ACCOUNT_ID,
        FAKE_CLOCK_START,
    )
    assert proposal.request.body == RESTORED_DRAFT_TEXT
    assert json.loads(response.body) == {"proposal_id": str(proposal.proposal_id)}
    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.AWAITING_APPROVAL


async def test_a_proposal_gives_its_records_the_time_of_one_clock_read() -> None:
    harness = with_ticking_clock(ready_harness())

    await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    (entry,) = harness.audit.entries
    assert {stored_proposal(harness).created_at, entry.occurred_at} == {FAKE_CLOCK_START}


async def test_a_proposal_reaches_no_customer_and_records_no_decision() -> None:
    harness = ready_harness()

    await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    assert harness.replies.replies == {}
    assert harness.replies.decisions == []


async def test_a_proposal_writes_its_audit_entry_with_identifiers_only() -> None:
    harness = ready_harness()

    await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    (entry,) = harness.audit.entries
    assert (entry.event_type, entry.actor_account_id, entry.ticket_id) == (
        AuditEventType.REPLY_PROPOSAL_SUBMITTED,
        STAFF_ACCOUNT_ID,
        TICKET_ID,
    )
    assert entry.data == {
        "proposal_id": str(stored_proposal(harness).proposal_id),
        "basis": "ai_draft",
    }


async def test_a_proposal_records_its_event_after_the_commit() -> None:
    harness = ready_harness()

    await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    (event,) = harness.events.of(EventName.REPLY_PROPOSAL_SUBMITTED)
    assert event.attributes == {"ticket_id": TICKET_ID}
    assert harness.transactions.commit_count == 1


async def test_a_proposal_keeps_the_reason_codes_and_the_note_of_staff() -> None:
    harness = ready_harness()
    proposal = RejectedAiDraftReply(OWN_TEXT, SUGGESTION_ID, (StaffReasonCode.OTHER,), NOTE)

    await build_propose(harness).execute(STAFF, TICKET_ID, proposal, KEY)

    request = stored_proposal(harness).request
    assert (request.staff_reason_codes, request.note) == ((StaffReasonCode.OTHER,), NOTE)


async def test_a_proposal_without_a_draft_is_valid_when_the_ai_abstained() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket()),
        build_ready_suggestion(build_no_draft(NoDraftStatus.ABSTAINED)),
    )

    await build_propose(harness).execute(
        STAFF, TICKET_ID, NoAiDraftReply(OWN_TEXT, SUGGESTION_ID), KEY
    )

    assert stored_proposal(harness).request.suggestion_id == SUGGESTION_ID


async def test_a_manual_ticket_takes_a_proposal_without_a_draft() -> None:
    harness = build_console_harness(build_console_ticket(handling_mode=HandlingMode.MANUAL))

    await build_propose(harness).execute(STAFF, TICKET_ID, NoAiDraftReply(OWN_TEXT, None), KEY)

    assert harness.tickets.tickets[TICKET_ID].status is TicketStatus.AWAITING_APPROVAL
    assert harness.ai_service.requests == ()


async def test_a_manual_ticket_refuses_a_proposal_that_names_a_suggestion() -> None:
    harness = build_console_harness(build_console_ticket(handling_mode=HandlingMode.MANUAL))

    with pytest.raises(SuggestionSupersededError):
        await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    assert_nothing_proposed(harness)


async def test_a_repeated_proposal_with_the_same_key_stores_nothing_more() -> None:
    harness = ready_harness()
    propose = build_propose(harness)
    first = await propose.execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    repeated = await propose.execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    assert repeated == first
    assert len(harness.audit.entries) == 1
    assert len(harness.events.of(EventName.REPLY_PROPOSAL_SUBMITTED)) == 1


async def test_a_key_reused_with_another_body_is_refused() -> None:
    harness = ready_harness()
    propose = build_propose(harness)
    await propose.execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    with pytest.raises(IdempotencyKeyReusedError):
        await propose.execute(STAFF, TICKET_ID, ai_draft_proposal(OWN_TEXT), KEY)

    assert stored_proposal(harness).request.body == RESTORED_DRAFT_TEXT


async def test_a_manager_may_not_propose_and_the_refusal_is_recorded() -> None:
    harness = ready_harness()

    with pytest.raises(ForbiddenRoleError):
        build_propose(harness).authorize(SIGNED_IN_MANAGER)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": MANAGER_ACCOUNT_ID,
        "role": "manager",
        "operation_id": "createReplyProposal",
    }


@pytest.mark.parametrize(("principal", "role"), REFUSED_ROLES)
async def test_customers_and_admins_may_not_propose(principal: Principal, role: str) -> None:
    harness = ready_harness()

    with pytest.raises(ForbiddenRoleError):
        build_propose(harness).authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert (denied.attributes["role"], denied.attributes["operation_id"]) == (
        role,
        "createReplyProposal",
    )


async def test_staff_are_allowed_to_propose_without_an_event() -> None:
    harness = ready_harness()

    support = build_propose(harness).authorize(SIGNED_IN_STAFF)

    assert support == STAFF
    assert harness.events.of(EventName.PERMISSION_DENIED) == ()


async def test_a_proposal_for_an_unknown_ticket_is_not_found() -> None:
    harness = ready_harness()

    with pytest.raises(TicketNotFoundError):
        await build_propose(harness).execute(
            STAFF, UNKNOWN_TICKET_ID, NoAiDraftReply(OWN_TEXT, None), KEY
        )

    assert_nothing_proposed(harness)


@pytest.mark.parametrize("status", NOT_OPEN)
async def test_a_ticket_that_is_not_open_refuses_a_proposal(status: TicketStatus) -> None:
    harness = build_console_harness(build_console_ticket(status=status))

    with pytest.raises(InvalidTicketStateError):
        await build_propose(harness).execute(STAFF, TICKET_ID, NoAiDraftReply(OWN_TEXT, None), KEY)

    assert harness.proposals.proposals == {}
    assert harness.tickets.tickets[TICKET_ID].status is status


async def test_the_state_is_checked_before_a_pending_part() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(status=TicketStatus.ESCALATED)),
        build_suggestion(),
    )

    with pytest.raises(InvalidTicketStateError):
        await build_propose(harness).execute(STAFF, TICKET_ID, NoAiDraftReply(OWN_TEXT, None), KEY)


async def test_a_pending_part_refuses_a_proposal_before_a_superseded_suggestion() -> None:
    harness = with_suggestion(build_console_harness(build_console_ticket()), build_suggestion())
    proposal = ai_draft_proposal(suggestion_id=OTHER_SUGGESTION_ID)

    with pytest.raises(SuggestionPendingError):
        await build_propose(harness).execute(STAFF, TICKET_ID, proposal, KEY)

    assert_nothing_proposed(harness)


async def test_a_superseded_suggestion_is_refused_before_the_body_rules() -> None:
    harness = ready_harness()
    proposal = ai_draft_proposal(DRAFT_TEXT, suggestion_id=OTHER_SUGGESTION_ID)

    with pytest.raises(SuggestionSupersededError):
        await build_propose(harness).execute(STAFF, TICKET_ID, proposal, KEY)

    assert_nothing_proposed(harness)


async def test_a_proposal_without_a_draft_is_refused_while_the_draft_is_ready() -> None:
    harness = ready_harness()

    with pytest.raises(ReplyBasisInvalidError) as caught:
        await build_propose(harness).execute(STAFF, TICKET_ID, NoAiDraftReply(OWN_TEXT, None), KEY)

    assert caught.value.detail == (
        "The basis no_ai_draft is not valid while the current draft is draft_ready."
    )
    assert_nothing_proposed(harness)


async def test_a_proposal_on_a_draft_is_refused_without_a_ready_draft() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket()),
        build_ready_suggestion(build_no_draft(NoDraftStatus.ABSTAINED)),
    )

    with pytest.raises(ReplyBasisInvalidError):
        await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    assert_nothing_proposed(harness)


async def test_a_proposal_on_a_draft_acknowledges_every_warning() -> None:
    harness = with_suggestion(
        build_console_harness(build_console_ticket(), restorer=RESTORER),
        build_suggestion(
            analysis=build_analysis(warning_ids=(WARNING_ID,)),
            draft=build_draft_ready((0, DRAFT_TEXT)),
        ),
    )

    with pytest.raises(WarningsNotAcknowledgedError):
        await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(), KEY)

    assert_nothing_proposed(harness)


async def test_a_proposal_with_other_needs_a_note() -> None:
    harness = ready_harness()
    proposal = RejectedAiDraftReply(OWN_TEXT, SUGGESTION_ID, (StaffReasonCode.OTHER,), None)

    with pytest.raises(NoteRequiredError):
        await build_propose(harness).execute(STAFF, TICKET_ID, proposal, KEY)

    assert_nothing_proposed(harness)


async def test_a_proposal_with_a_placeholder_is_refused_and_stored_nowhere() -> None:
    harness = ready_harness(is_authority_required=True)

    with pytest.raises(PlaceholderInBodyError):
        await build_propose(harness).execute(STAFF, TICKET_ID, ai_draft_proposal(DRAFT_TEXT), KEY)

    assert_nothing_proposed(harness)
    assert harness.audit.entries == []


async def test_a_proposal_after_a_refused_one_is_stored_with_a_new_key() -> None:
    harness = ready_harness()
    propose = build_propose(harness)
    with pytest.raises(PlaceholderInBodyError):
        await propose.execute(STAFF, TICKET_ID, ai_draft_proposal(DRAFT_TEXT), KEY)

    await propose.execute(STAFF, TICKET_ID, ai_draft_proposal(), OTHER_KEY)

    assert stored_proposal(harness).request.body == RESTORED_DRAFT_TEXT
