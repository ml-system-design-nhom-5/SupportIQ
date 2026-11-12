"""The request of a suggestion, built from the pseudonymized message and the order facts."""

from supportiq_backend.commerce import Order
from supportiq_backend.suggestions.domain.ai_results import OrderContext, SuggestionRequest
from supportiq_backend.suggestions.domain.ports import TicketMessage
from supportiq_backend.suggestions.domain.suggestions import Suggestion


def build_order_context(order: Order) -> OrderContext:
    """Keep only the allow-listed facts of an order (contracts v1 design, `OrderContext`).

    No identifier, no address, and no line leaves backend (SEC-04).

    Args:
        order: The ticket's order.

    Returns:
        The order context.
    """
    refund = order.refund
    return OrderContext(
        order_status=order.status,
        placed_at=order.placed_at,
        order_total=order.order_total,
        shipping_cost=order.shipping_cost,
        shipment_status=order.shipment.status,
        estimated_delivery_at=order.shipment.estimated_delivery_at,
        delivered_at=order.shipment.delivered_at,
        refund_status=None if refund is None else refund.status,
        refund_amount=None if refund is None else refund.amount,
        refund_requested_at=None if refund is None else refund.requested_at,
    )


def build_suggestion_request(
    suggestion: Suggestion,
    ticket: TicketMessage,
    pseudonymized_message: str,
    order: Order | None,
) -> SuggestionRequest:
    """Build the request that both calls of a suggestion send.

    Args:
        suggestion: The suggestion, whose override the request carries.
        ticket: The ticket, whose `created_at` is `as_of`.
        pseudonymized_message: The message after pseudonymization.
        order: The ticket's order, when it has one.

    Returns:
        The request.
    """
    return SuggestionRequest(
        message=pseudonymized_message,
        order_context=None if order is None else build_order_context(order),
        as_of=ticket.created_at,
        intent_override=suggestion.intent_override,
    )
