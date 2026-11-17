"""What the console's actions record: audit entries, staff decisions, and events.

`sendReply`, `createReplyProposal`, and `createEscalation` write their audit entries and
their staff decision the same way, here (CODE-52). An entry holds identifiers, statuses,
reason codes, and numbers only, never a body or a note (contracts v1 design, Audit log), and
an event holds allow-listed Internal values only (LOG-29). An action reads the clock once, so
every record that it writes holds the same time.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from supportiq_backend.accounts import AccountId, DisplayName, SupportPrincipal
from supportiq_backend.audit import (
    ActorAccountId,
    AuditEntry,
    AuditEntryId,
    AuditEventType,
    AuditTicketId,
    AuditValue,
)
from supportiq_backend.platform import EventAttributeValue, EventName, SpanName
from supportiq_backend.tickets.application.console_ports import ConsolePorts, ConsoleStores
from supportiq_backend.tickets.domain import (
    ConsoleTicket,
    DecisionId,
    RecordedDecision,
    SentProposal,
    StaffDecision,
    StaffReasonCode,
    TicketId,
    is_proposal_changed,
)

# Audit values and canonical request fields are scalars, so a list is joined into one text.
LIST_SEPARATOR = ","
# `change_ratio` has three decimals, so thousandths hold it exactly.
CHANGE_RATIO_SCALE = 1_000


@dataclass(frozen=True, slots=True)
class ActionContext:
    """Who acts on which ticket, and when: the one time of every record of the action.

    Attributes:
        ticket_id: The ticket, locked by the action's transaction.
        actor: The staff member or manager who acts.
        acted_at: When the action runs, read once from the clock after the checks.
    """

    ticket_id: TicketId
    actor: AccountId
    acted_at: datetime


def begin_action(
    ports: ConsolePorts, ticket: ConsoleTicket, support: SupportPrincipal
) -> ActionContext:
    """Read the clock once for every record of the caller's action on the ticket.

    Args:
        ports: The ports of the use case.
        ticket: The ticket, locked, that passed every check.
        support: The caller.

    Returns:
        The ticket, the caller, and the time of the action.
    """
    return ActionContext(ticket.ticket_id, support.account_id, ports.clock.now())


def join_reason_codes(codes: Iterable[StaffReasonCode]) -> str:
    """Join staff reason codes into one scalar value, in their order.

    Args:
        codes: The codes.

    Returns:
        The values, separated by commas; empty without a code.
    """
    return LIST_SEPARATOR.join(code.value for code in codes)


def build_audit_entry(
    ports: ConsolePorts,
    action: ActionContext,
    event_type: AuditEventType,
    data: Mapping[str, AuditValue],
) -> AuditEntry:
    """Build an audit entry of a console action, in the trace of the request.

    Args:
        ports: The ports of the use case.
        action: The ticket, the actor, and the time of the action.
        event_type: What happened.
        data: Identifiers, statuses, reason codes, and numbers only.

    Returns:
        The entry, for the audit log of the action's transaction.
    """
    return AuditEntry(
        entry_id=AuditEntryId(ports.ids.generate()),
        occurred_at=action.acted_at,
        event_type=event_type,
        actor_account_id=ActorAccountId(action.actor),
        ticket_id=AuditTicketId(action.ticket_id),
        trace_id=ports.traces.current_trace_id(),
        data=data,
    )


def build_recorded_decision(
    ports: ConsolePorts,
    action: ActionContext,
    decision: StaffDecision,
    sent: SentProposal | None,
) -> RecordedDecision:
    """Build the decision record of an action; a reply from a proposal names both accounts.

    Args:
        ports: The ports of the use case.
        action: The ticket, the staff member or manager who sent or escalated, and the time.
        decision: What was decided.
        sent: The proposal that a manager sends, for a reply from a proposal.

    Returns:
        The record, with its new ID and the time of the action.
    """
    return RecordedDecision(
        decision_id=DecisionId(ports.ids.generate()),
        ticket_id=action.ticket_id,
        decision=decision,
        decided_by=action.actor,
        proposed_by=None if sent is None else sent.proposal.proposed_by,
        is_proposal_changed=None if sent is None else is_proposal_changed(sent),
        decided_at=action.acted_at,
    )


async def save_decision(
    stores: ConsoleStores, ports: ConsolePorts, decision: RecordedDecision
) -> None:
    """Insert a staff decision and its `decision.recorded` entry, in the step's span.

    Args:
        stores: The stores of the action's transaction.
        ports: The ports of the use case.
        decision: The decision record; its entry holds the same time.
    """
    with ports.steps.step(SpanName.SAVE_DECISION):
        await stores.replies.insert_decision(decision)
        action = ActionContext(decision.ticket_id, decision.decided_by, decision.decided_at)
        await stores.audit.append(
            build_audit_entry(
                ports, action, AuditEventType.DECISION_RECORDED, _decision_data(decision.decision)
            )
        )


async def load_display_name(stores: ConsoleStores, account_id: AccountId) -> DisplayName:
    """Load the display name of the staff member or manager who acts.

    Args:
        stores: The stores of the action's transaction.
        account_id: The account of the caller.

    Returns:
        The name; the session of the caller makes the account present.
    """
    names = await stores.staff.load_display_names(frozenset({account_id}))
    return names[account_id]


def record_decision_event(
    ports: ConsolePorts, ticket_id: TicketId, decision: StaffDecision
) -> None:
    """Record `decision.recorded`, after the commit of the action.

    Args:
        ports: The ports of the use case.
        ticket_id: The ticket.
        decision: What was decided.
    """
    attributes: dict[str, EventAttributeValue] = {
        "ticket_id": ticket_id,
        "decision_type": decision.decision_type.value,
    }
    if decision.suggestion_id is not None:
        attributes["suggestion_id"] = decision.suggestion_id
    ports.events.record(EventName.DECISION_RECORDED, **attributes)


def _decision_data(decision: StaffDecision) -> Mapping[str, AuditValue]:
    data: dict[str, AuditValue] = {
        "decision_type": decision.decision_type.value,
        "staff_reason_codes": join_reason_codes(decision.staff_reason_codes),
    }
    if decision.suggestion_id is not None:
        data["suggestion_id"] = decision.suggestion_id
    if decision.change_ratio is not None:
        # Audit values are scalars without fractions, so the ratio is kept in thousandths.
        data["change_ratio_thousandths"] = round(decision.change_ratio * CHANGE_RATIO_SCALE)
    return data
