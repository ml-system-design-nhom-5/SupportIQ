"""The mapping from the contract's `SuggestionRequest` to the domain request.

The generated model has already checked every field against its schema in strict mode. This
module adds what the generated model cannot check: every timestamp, `as_of` included, is a
contract `Timestamp` in UTC with `Z`, and a time without a time zone is rejected.
"""

from datetime import datetime

from pydantic import MISSING

from app.generated import Money, OrderContext, SuggestionRequest
from app.platform.web import parse_timestamp
from app.suggestions.domain import (
    IntentName,
    MoneyAmount,
    OrderFacts,
    SuggestionInput,
)

_ORDER_CONTEXT_LOCATION = "body.order_context."


def suggestion_input(body: SuggestionRequest) -> SuggestionInput:
    """Map the body of `createAnalysis` or `createDraft` to the domain request.

    Args:
        body: The body, parsed strictly into the generated model.

    Returns:
        The domain request.

    Raises:
        RequestContractError: A timestamp is not a contract `Timestamp`.
    """
    return SuggestionInput(
        message=body.message.root,
        as_of=parse_timestamp(body.as_of, "body.as_of"),
        order_facts=None if body.order_context is MISSING else order_facts(body.order_context),
        kb_version=None if body.kb_version is MISSING else body.kb_version.root,
        intent_override=(
            None if body.intent_override is MISSING else IntentName(body.intent_override.value)
        ),
    )


def order_facts(context: OrderContext) -> OrderFacts:
    """Map the allow-listed order context to the order facts.

    Args:
        context: The order context of the request.

    Returns:
        The order facts; an absent field stays None.

    Raises:
        RequestContractError: A timestamp field is not a contract `Timestamp`.
    """
    return OrderFacts(
        order_status=None if context.order_status is MISSING else context.order_status.value,
        placed_at=_timestamp_of(context.placed_at, "placed_at"),
        order_total=_money_of(context.order_total),
        shipping_cost=_money_of(context.shipping_cost),
        shipment_status=(
            None if context.shipment_status is MISSING else context.shipment_status.value
        ),
        estimated_delivery_at=_timestamp_of(context.estimated_delivery_at, "estimated_delivery_at"),
        delivered_at=_timestamp_of(context.delivered_at, "delivered_at"),
        refund_status=None if context.refund_status is MISSING else context.refund_status.value,
        refund_amount=_money_of(context.refund_amount),
        refund_requested_at=_timestamp_of(context.refund_requested_at, "refund_requested_at"),
    )


def _timestamp_of(value: str | MISSING, field_name: str) -> datetime | None:
    if value is MISSING:
        return None
    return parse_timestamp(value, _ORDER_CONTEXT_LOCATION + field_name)


def _money_of(value: Money | MISSING) -> MoneyAmount | None:
    if value is MISSING:
        return None
    return MoneyAmount(amount_minor=value.amount_minor, currency=value.currency)
