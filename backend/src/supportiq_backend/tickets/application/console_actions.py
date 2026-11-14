"""What the console's actions record: audit entries, staff decisions, and events.

`sendReply`, `createReplyProposal`, and `createEscalation` write their audit entries and
their staff decision the same way, here (CODE-52). An entry holds identifiers, statuses,
reason codes, and numbers only, never a body or a note (contracts v1 design, Audit log), and
an event holds allow-listed Internal values only (LOG-29).
"""

from collections.abc import Iterable, Mapping

from supportiq_backend.accounts import (
    AccountId,
)
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
    ticket_id: TicketId,
    actor: AccountId,
    event_type: AuditEventType,
    data: Mapping[str, AuditValue],
) -> AuditEntry:
    """Build an audit entry of a console action, in the trace of the request.

    Args:
        ports: The ports of the use case.
        ticket_id: The ticket.
        actor: The staff member or manager who acted.
        event_type: What happened.
        data: Identifiers, statuses, reason codes, and numbers only.

    Returns:
        The entry, for the audit log of the action's transaction.
    """
    return AuditEntry(
        entry_id=AuditEntryId(ports.ids.generate()),
        occurred_at=ports.clock.now(),
        event_type=event_type,
        actor_account_id=ActorAccountId(actor),
        ticket_id=AuditTicketId(ticket_id),
        trace_id=ports.traces.current_trace_id(),
        data=data,
    )


def build_recorded_decision(
    ports: ConsolePorts,
    ticket_id: TicketId,
    decided_by: AccountId,
    decision: StaffDecision,
    sent: SentProposal | None,
) -> RecordedDecision:
    """Build the decision record of an action; a reply from a proposal names both accounts.

    Args:
        ports: The ports of the use case.
        ticket_id: The ticket.
        decided_by: The staff member or manager who sent or escalated.
        decision: What was decided.
        sent: The proposal that a manager sends, for a reply from a proposal.

    Returns:
        The record, with its new ID and the time of now.
    """
    return RecordedDecision(
        decision_id=DecisionId(ports.ids.generate()),
        ticket_id=ticket_id,
        decision=decision,
        decided_by=decided_by,
        proposed_by=None if sent is None else sent.proposal.proposed_by,
        is_proposal_changed=None if sent is None else is_proposal_changed(sent),
        decided_at=ports.clock.now(),
    )


async def save_decision(
    stores: ConsoleStores, ports: ConsolePorts, decision: RecordedDecision
) -> None:
    """Insert a staff decision and its `decision.recorded` entry, in the step's span.

    Args:
        stores: The stores of the action's transaction.
        ports: The ports of the use case.
        decision: The decision record.
    """
    with ports.steps.step(SpanName.SAVE_DECISION):
        await stores.replies.insert_decision(decision)
        await stores.audit.append(
            build_audit_entry(
                ports,
                decision.ticket_id,
                decision.decided_by,
                AuditEventType.DECISION_RECORDED,
                _decision_data(decision.decision),
            )
        )


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
