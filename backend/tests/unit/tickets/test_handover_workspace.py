"""Tests of the workspace after a reply proposal or an escalation, with fakes of every port.

The workspace shows the proposal once staff submit one and the escalation once staff
escalate, also after the ticket is closed, each with the display name of the staff member
(contract `TicketWorkspace`).
"""

from uuid import UUID

import pytest

from supportiq_backend.idempotency import IdempotencyKey
from supportiq_backend.tickets import (
    EscalationRecord,
    EscalationRequest,
    NoAiDraftReply,
    ProposalRecord,
    ProposalReply,
    StaffReasonCode,
    TicketAction,
)
from tests.unit.tickets.console_fakes import (
    KEY,
    MANAGER,
    SIGNED_IN_MANAGER,
    SIGNED_IN_STAFF,
    STAFF,
    TICKET_ID,
    ConsoleHarness,
    build_console_harness,
    build_console_ticket,
    build_escalate,
    build_get,
    build_propose,
    build_send,
)
from tests.unit.tickets.fakes import MANAGER_NAME, STAFF_NAME

pytestmark = pytest.mark.anyio

PROPOSED_TEXT = "A manager will confirm the shipping options for your city."
REPLY_TEXT = "We ship to your city for free."
SEND_KEY = IdempotencyKey(UUID("00000000-0000-4000-8000-000000000124"))
ESCALATION = EscalationRequest((StaffReasonCode.CASE_EXCEPTION,), None, None)


async def proposed_harness() -> ConsoleHarness:
    harness = build_console_harness(build_console_ticket())
    await build_propose(harness).execute(STAFF, TICKET_ID, NoAiDraftReply(PROPOSED_TEXT, None), KEY)
    return harness


async def escalated_harness() -> ConsoleHarness:
    harness = build_console_harness(build_console_ticket())
    await build_escalate(harness).execute(STAFF, TICKET_ID, ESCALATION, KEY)
    return harness


async def test_the_workspace_of_an_open_ticket_has_no_proposal_and_no_escalation() -> None:
    harness = build_console_harness(build_console_ticket())

    workspace = await build_get(harness).execute(SIGNED_IN_STAFF, TICKET_ID)

    assert (workspace.proposal, workspace.escalation, workspace.reply) == (None, None, None)


async def test_a_manager_sees_the_proposal_with_the_name_of_staff_and_may_send_it() -> None:
    harness = await proposed_harness()

    workspace = await build_get(harness).execute(SIGNED_IN_MANAGER, TICKET_ID)

    proposal = harness.proposals.proposals[TICKET_ID]
    assert workspace.proposal == ProposalRecord(proposal, STAFF_NAME)
    assert (workspace.escalation, workspace.reply) == (None, None)
    assert workspace.allowed_actions == {TicketAction.SEND_REPLY}


async def test_staff_see_their_proposal_and_may_take_no_action() -> None:
    harness = await proposed_harness()

    workspace = await build_get(harness).execute(SIGNED_IN_STAFF, TICKET_ID)

    assert workspace.proposal == ProposalRecord(harness.proposals.proposals[TICKET_ID], STAFF_NAME)
    assert workspace.allowed_actions == frozenset()


async def test_a_manager_sees_the_escalation_with_the_name_of_staff() -> None:
    harness = await escalated_harness()

    workspace = await build_get(harness).execute(SIGNED_IN_MANAGER, TICKET_ID)

    escalation = harness.escalations.escalations[TICKET_ID]
    assert workspace.escalation == EscalationRecord(escalation, STAFF_NAME)
    assert workspace.proposal is None
    assert workspace.allowed_actions == {TicketAction.SEND_REPLY}


async def test_a_closed_ticket_still_shows_its_proposal_next_to_the_reply() -> None:
    harness = await proposed_harness()
    proposal = harness.proposals.proposals[TICKET_ID]
    await build_send(harness).execute(
        MANAGER, TICKET_ID, ProposalReply(PROPOSED_TEXT, proposal.proposal_id), SEND_KEY
    )

    workspace = await build_get(harness).execute(SIGNED_IN_STAFF, TICKET_ID)

    assert workspace.proposal == ProposalRecord(proposal, STAFF_NAME)
    assert workspace.reply is not None
    assert workspace.reply.sent_by_display_name == MANAGER_NAME


async def test_a_closed_ticket_still_shows_its_escalation_next_to_the_reply() -> None:
    harness = await escalated_harness()
    await build_send(harness).execute(
        MANAGER, TICKET_ID, NoAiDraftReply(REPLY_TEXT, None), SEND_KEY
    )

    workspace = await build_get(harness).execute(SIGNED_IN_MANAGER, TICKET_ID)

    assert workspace.escalation == EscalationRecord(
        harness.escalations.escalations[TICKET_ID], STAFF_NAME
    )
    assert workspace.reply is not None
    assert workspace.reply.reply.body == REPLY_TEXT
