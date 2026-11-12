"""Map the console's tickets to `backend` contract 1.2.0: queue summaries, workspace, reply.

Pseudonyms are already restored in the texts that reach this module (ADR-0010). The console's
order views repeat the shop's order schemas, so they reuse the shop's order mapping, which
the composition root passes in: tickets never imports the interface of commerce (ARCH-17,
ARCH-21, ARCH-22).
"""

from datetime import datetime

from pydantic import MISSING

from supportiq_backend.commerce import AddressedOrder, Order
from supportiq_backend.generated import ConfidenceBand as ContractConfidenceBand
from supportiq_backend.generated import (
    ConsoleCustomerView,
    ConsoleMessageView,
    ConsoleOrderView,
    ConsoleOtherOrderView,
    ConsoleReplyView,
    ConsoleTicketStatus,
    MessageText,
    ReplyBody,
    StaffMemberView,
    TicketSummaryIntent,
)
from supportiq_backend.generated import DraftStatus as ContractDraftStatus
from supportiq_backend.generated import HandlingMode as ContractHandlingMode
from supportiq_backend.generated import IntentLabel as ContractIntentLabel
from supportiq_backend.generated import RefundStatus as ContractRefundStatus
from supportiq_backend.generated import ReplyBasis as ContractReplyBasis
from supportiq_backend.generated import ShipmentStatus as ContractShipmentStatus
from supportiq_backend.generated import TicketAction as ContractTicketAction
from supportiq_backend.generated import TicketSummary as ContractTicketSummary
from supportiq_backend.generated import TicketWorkspace as ContractTicketWorkspace
from supportiq_backend.platform.web import format_timestamp
from supportiq_backend.suggestions import get_part_status
from supportiq_backend.tickets.api.console_suggestion_views import to_suggestion_view
from supportiq_backend.tickets.api.order_views import OrderViewMappers
from supportiq_backend.tickets.domain import ReplyRecord, TicketSummary, TicketWorkspace


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
        handling_started_at=_optional_time(ticket.handling_started_at),
        closed_at=_optional_time(ticket.closed_at),
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


def to_workspace(
    workspace: TicketWorkspace, order_views: OrderViewMappers
) -> ContractTicketWorkspace:
    """Map the ticket workspace to the contract.

    Args:
        workspace: The workspace, with the AI text restored.
        order_views: The order mappings of commerce, for the orders and the order facts.

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
        handling_started_at=_optional_time(ticket.handling_started_at),
        closed_at=_optional_time(ticket.closed_at),
        customer=ConsoleCustomerView(display_name=workspace.customer_display_name),
        message=ConsoleMessageView(
            body=MessageText(ticket.message), created_at=format_timestamp(ticket.created_at)
        ),
        order=MISSING if workspace.order is None else _to_order(workspace.order, order_views),
        other_orders=(
            [_to_other_order(order, order_views) for order in workspace.other_orders]
            if workspace.other_orders
            else MISSING
        ),
        suggestion=(
            MISSING
            if workspace.suggestion is None
            else to_suggestion_view(workspace.suggestion, order_views)
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


def _optional_time(moment: datetime | None) -> str | MISSING:
    return MISSING if moment is None else format_timestamp(moment)
