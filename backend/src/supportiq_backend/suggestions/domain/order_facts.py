"""The facts of an order context, and the check that a draft cites only facts it was sent.

`ai-service` never returns a draft that cites an order field absent from the request: such a
draft is `grounding_failed` (contracts v1 design, Errors). A draft that does so anyway is a
response outside the contract, so its part becomes unavailable instead of being stored with
a citation that the workspace cannot show (backend ticket workflow design, The `ai-service`
client).
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


def check_cited_facts(outcome: DraftOutcome, context: OrderContext | None) -> None:
    """Refuse a draft that cites an order field without a value in the request's context.

    Args:
        outcome: The draft outcome that ai-service returned.
        context: The order context that the request carried; absent without an order.

    Raises:
        AiServiceContractError: An order citation names a field that was not sent.
    """
    if not isinstance(outcome, DraftReady):
        return
    for citation in outcome.draft.citations:
        if not isinstance(citation, OrderContextCitation):
            continue
        if context is None or read_order_fact(context, citation.field) is None:
            raise AiServiceContractError
