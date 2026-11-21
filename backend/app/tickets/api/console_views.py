"""Map the console's tickets to `backend` contract 1.2.0: queues, workspace, and staff actions.

Pseudonyms are already restored in the texts that reach this module (ADR-0010). The console's
order views repeat the shop's order schemas, and its asset versions repeat those of the admin
area, so they reuse the mappings of commerce and suggestions, which the composition root
passes in: tickets never imports the interface of another feature (ARCH-17, ARCH-21, ARCH-22).
"""

from pydantic import MISSING

from app.commerce import AddressedOrder, Order
from app.generated import ConfidenceBand as ContractConfidenceBand
from app.generated import (
    ConsoleCustomerView,
    ConsoleMessageView,
    ConsoleOrderView,
    ConsoleOtherOrderView,
    ConsoleReplyView,
    ConsoleTicketStatus,
    EscalationView,
    MessageText,
    ReplyBody,
    ReplyProposalView,
    StaffMemberView,
    StaffNoteText,
    TicketSummaryIntent,
)
from app.generated import DraftStatus as ContractDraftStatus
from app.generated import HandlingMode as ContractHandlingMode
from app.generated import IntentLabel as ContractIntentLabel
from app.generated import RefundStatus as ContractRefundStatus
from app.generated import ReplyBasis as ContractReplyBasis
from app.generated import ReplyProposalBasis as ContractReplyProposalBasis
from app.generated import ShipmentStatus as ContractShipmentStatus
from app.generated import StaffReasonCode as ContractStaffReasonCode
from app.generated import TicketAction as ContractTicketAction
from app.generated import TicketSummary as ContractTicketSummary
from app.generated import TicketWorkspace as ContractTicketWorkspace
from app.platform.web import format_optional_timestamp, format_timestamp
from app.suggestions import get_part_status
from app.tickets.api.console_suggestion_views import to_suggestion_view
from app.tickets.api.console_view_mappers import ConsoleViewMappers
from app.tickets.api.order_views import OrderViewMappers
from app.tickets.domain import (
    EscalationRecord,
    ProposalRecord,
    ReplyRecord,
    StaffReasonCode,
    TicketSummary,
    TicketWorkspace,
)


def to_ticket_summary(summary: TicketSummary) -> ContractTicketSummary:
    """Map one ticket of a queue to the contract.

    Args:
        summary: The ticket, its customer's name, and its current suggestion.

    Returns:
        The contract model; the draft status is absent in manual mode, and the predicted
        intent is absent without a model analysis.
    """
    ticket = summary.ticket
    suggestion = summary.suggestion
    predicted = None if suggestion is None else suggestion.predicted_intent
    return ContractTicketSummary(
        ticket_id=ticket.ticket_id,
        created_at=format_timestamp(ticket.created_at),
        status=ConsoleTicketStatus(ticket.status.value),
        handling_mode=ContractHandlingMode(ticket.handling_mode.value),
        is_authority_required=ticket.is_authority_required,
        handling_started_at=format_optional_timestamp(ticket.handling_started_at),
        closed_at=format_optional_timestamp(ticket.closed_at),
        customer=ConsoleCustomerView(display_name=summary.customer_display_name),
        message_excerpt=ticket.message_excerpt,
        draft_status=(
            MISSING
            if suggestion is None
            else ContractDraftStatus(get_part_status(suggestion.draft).value)
        ),
        predicted_intent=(
            MISSING
            if predicted is None
            else TicketSummaryIntent(
                label=ContractIntentLabel(predicted.label.value),
                probability=predicted.probability,
                confidence_band=ContractConfidenceBand(predicted.confidence_band.value),
            )
        ),
    )


def to_workspace(workspace: TicketWorkspace, views: ConsoleViewMappers) -> ContractTicketWorkspace:
    """Map the ticket workspace to the contract.

    Args:
        workspace: The workspace, with the AI text restored.
        views: The mappings of other features, for the orders, the order facts, and the
            asset versions.

    Returns:
        The contract model.

    Raises:
        UnexpectedFailureError: The current suggestion breaks an invariant of its parts: a
            defect.
    """
    ticket = workspace.ticket
    return ContractTicketWorkspace(
        ticket_id=ticket.ticket_id,
        status=ConsoleTicketStatus(ticket.status.value),
        handling_mode=ContractHandlingMode(ticket.handling_mode.value),
        is_authority_required=ticket.is_authority_required,
        created_at=format_timestamp(ticket.created_at),
        handling_started_at=format_optional_timestamp(ticket.handling_started_at),
        closed_at=format_optional_timestamp(ticket.closed_at),
        customer=ConsoleCustomerView(display_name=workspace.customer_display_name),
        message=ConsoleMessageView(
            body=MessageText(ticket.message), created_at=format_timestamp(ticket.created_at)
        ),
        order=MISSING if workspace.order is None else _to_order(workspace.order, views.orders),
        other_orders=(
            [_to_other_order(order, views.orders) for order in workspace.other_orders]
            if workspace.other_orders
            else MISSING
        ),
        suggestion=(
            MISSING
            if workspace.suggestion is None
            else to_suggestion_view(workspace.suggestion, views)
        ),
        proposal=MISSING if workspace.proposal is None else to_proposal_view(workspace.proposal),
        escalation=(
            MISSING if workspace.escalation is None else to_escalation_view(workspace.escalation)
        ),
        reply=MISSING if workspace.reply is None else to_reply_view(workspace.reply),
        allowed_actions=sorted(
            (ContractTicketAction(action.value) for action in workspace.allowed_actions),
            key=lambda action: action.value,
        ),
    )


def to_reply_view(record: ReplyRecord) -> ConsoleReplyView:
    """Map a sent reply to the contract.

    Args:
        record: The reply and its sender's name.

    Returns:
        The contract model.
    """
    reply = record.reply
    return ConsoleReplyView(
        reply_id=str(reply.reply_id),
        basis=ContractReplyBasis(reply.basis.value),
        body=ReplyBody(MessageText(reply.body)),
        suggestion_id=MISSING if reply.suggestion_id is None else reply.suggestion_id,
        proposal_id=MISSING if reply.proposal_id is None else str(reply.proposal_id),
        sent_by=StaffMemberView(account_id=reply.sent_by, display_name=record.sent_by_display_name),
        sent_at=format_timestamp(reply.sent_at),
    )


def to_proposal_view(record: ProposalRecord) -> ReplyProposalView:
    """Map a reply proposal to the contract.

    Args:
        record: The proposal and the name of the staff member who submitted it.

    Returns:
        The contract model.
    """
    proposal = record.proposal
    request = proposal.request
    return ReplyProposalView(
        proposal_id=str(proposal.proposal_id),
        basis=ContractReplyProposalBasis(request.basis.value),
        body=ReplyBody(MessageText(request.body)),
        suggestion_id=MISSING if request.suggestion_id is None else request.suggestion_id,
        staff_reason_codes=_to_reason_codes(request.staff_reason_codes),
        note=_optional_note(request.note),
        proposed_by=StaffMemberView(
            account_id=proposal.proposed_by, display_name=record.proposed_by_display_name
        ),
        created_at=format_timestamp(proposal.created_at),
    )


def to_escalation_view(record: EscalationRecord) -> EscalationView:
    """Map an escalation to the contract.

    Args:
        record: The escalation and the name of the staff member who escalated.

    Returns:
        The contract model.
    """
    escalation = record.escalation
    request = escalation.request
    return EscalationView(
        escalation_id=str(escalation.escalation_id),
        staff_reason_codes=_to_reason_codes(request.staff_reason_codes),
        note=_optional_note(request.note),
        suggestion_id=MISSING if request.suggestion_id is None else request.suggestion_id,
        escalated_by=StaffMemberView(
            account_id=escalation.escalated_by, display_name=record.escalated_by_display_name
        ),
        escalated_at=format_timestamp(escalation.escalated_at),
    )


def _to_order(addressed: AddressedOrder, order_views: OrderViewMappers) -> ConsoleOrderView:
    shop_view = order_views.to_order_view(addressed.order)
    return ConsoleOrderView(
        order_id=shop_view.order_id,
        order_status=shop_view.order_status,
        placed_at=shop_view.placed_at,
        order_total=shop_view.order_total,
        shipping_cost=shop_view.shipping_cost,
        lines=shop_view.lines,
        shipment=shop_view.shipment,
        refund=shop_view.refund,
        shipping_address=addressed.shipping_address,
    )


def _to_other_order(order: Order, order_views: OrderViewMappers) -> ConsoleOtherOrderView:
    shop_view = order_views.to_order_view(order)
    return ConsoleOtherOrderView(
        order_id=shop_view.order_id,
        order_status=shop_view.order_status,
        shipment_status=ContractShipmentStatus(order.shipment.status.value),
        refund_status=(
            MISSING if order.refund is None else ContractRefundStatus(order.refund.status.value)
        ),
        placed_at=shop_view.placed_at,
        order_total=shop_view.order_total,
        lines=shop_view.lines,
    )


def _to_reason_codes(codes: tuple[StaffReasonCode, ...]) -> list[ContractStaffReasonCode]:
    return [ContractStaffReasonCode(code.value) for code in codes]


def _optional_note(note: str | None) -> StaffNoteText | MISSING:
    return MISSING if note is None else StaffNoteText(note)
