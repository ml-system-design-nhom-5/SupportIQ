"""The facts of an order context, and the facts that a draft cites from it.

`ai-service` never returns a draft that cites an order field absent from the request: such a
draft is `grounding_failed` (contracts v1 design, Errors). A draft that does so anyway is a
response outside the contract, so reading its cited facts fails and its part becomes
unavailable instead of being stored with a citation that the workspace cannot show (backend
ticket workflow design, The `ai-service` client).
"""

from collections.abc import Callable, Mapping
from datetime import datetime
from types import MappingProxyType

from supportiq_backend.commerce import Money, OrderStatus, RefundStatus, ShipmentStatus
from supportiq_backend.suggestions.domain.ai_results import (
    DraftOutcome,
    DraftReady,
    OrderContext,
    OrderContextCitation,
)
from supportiq_backend.suggestions.domain.errors import AiServiceContractError
from supportiq_backend.suggestions.domain.labels import OrderContextField

type OrderFact = OrderStatus | ShipmentStatus | RefundStatus | Money | datetime

_FACT_READERS: Mapping[OrderContextField, Callable[[OrderContext], OrderFact | None]] = (
    MappingProxyType(
        {
            OrderContextField.ORDER_STATUS: lambda context: context.order_status,
            OrderContextField.PLACED_AT: lambda context: context.placed_at,
            OrderContextField.ORDER_TOTAL: lambda context: context.order_total,
            OrderContextField.SHIPPING_COST: lambda context: context.shipping_cost,
            OrderContextField.SHIPMENT_STATUS: lambda context: context.shipment_status,
            OrderContextField.ESTIMATED_DELIVERY_AT: lambda context: context.estimated_delivery_at,
            OrderContextField.DELIVERED_AT: lambda context: context.delivered_at,
            OrderContextField.REFUND_STATUS: lambda context: context.refund_status,
            OrderContextField.REFUND_AMOUNT: lambda context: context.refund_amount,
            OrderContextField.REFUND_REQUESTED_AT: lambda context: context.refund_requested_at,
        }
    )
)


def read_order_fact(context: OrderContext, field: OrderContextField) -> OrderFact | None:
    """Return the value of one field of an order context.

    Args:
        context: The order context.
        field: The field that an order citation names.

    Returns:
        The value; absent when the context has none for the field.
    """
    return _FACT_READERS[field](context)


def read_cited_facts(outcome: DraftOutcome, context: OrderContext | None) -> tuple[OrderFact, ...]:
    """Return the facts that a ready draft cites, refusing a cited field that was not sent.

    Args:
        outcome: The draft outcome that ai-service returned.
        context: The order context that the request carried; absent without an order.

    Returns:
        The value of each order citation, in the order of the citations. Empty for a draft
        that cites only KB documents and for an outcome without a draft.

    Raises:
        AiServiceContractError: An order citation names a field that was not sent.
    """
    if not isinstance(outcome, DraftReady):
        return ()
    return tuple(
        _read_sent_fact(context, citation.field)
        for citation in outcome.draft.citations
        if isinstance(citation, OrderContextCitation)
    )


def _read_sent_fact(context: OrderContext | None, field: OrderContextField) -> OrderFact:
    fact = None if context is None else read_order_fact(context, field)
    if fact is None:
        raise AiServiceContractError
    return fact
