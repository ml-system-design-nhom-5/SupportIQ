"""The request of an analysis or a draft, after the interface layer validated it.

It carries no ticket ID, no customer identity, and no staff identity (SEC-04). The message
is pseudonymized text, which is still Confidential (ADR-0010).
"""

from dataclasses import dataclass
from datetime import datetime
from typing import NewType

# One of the 46 intent labels of the contract's `IntentLabel`. Internal.
IntentName = NewType("IntentName", str)


@dataclass(frozen=True, slots=True)
class MoneyAmount:
    """An amount of money in minor units, such as cents.

    Attributes:
        amount_minor: The amount in minor units.
        currency: The ISO 4217 code.
    """

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True)
class OrderFacts:
    """The allow-listed facts of the ticket's order; None means not applicable or unknown.

    Attributes:
        order_status: The status of the order.
        placed_at: When the order was placed.
        order_total: The total of the order.
        shipping_cost: The shipping cost.
        shipment_status: The status of the shipment.
        estimated_delivery_at: The estimated delivery time.
        delivered_at: When the order was delivered.
        refund_status: The status of the refund.
        refund_amount: The amount of the refund.
        refund_requested_at: When the refund was requested.
    """

    order_status: str | None = None
    placed_at: datetime | None = None
    order_total: MoneyAmount | None = None
    shipping_cost: MoneyAmount | None = None
    shipment_status: str | None = None
    estimated_delivery_at: datetime | None = None
    delivered_at: datetime | None = None
    refund_status: str | None = None
    refund_amount: MoneyAmount | None = None
    refund_requested_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SuggestionInput:
    """What `createAnalysis` and `createDraft` receive.

    Attributes:
        message: The customer's message after pseudonymization. Confidential.
        as_of: The point in time at which KB document validity is evaluated, in UTC.
        order_facts: The facts of the ticket's order; None when the ticket has no order.
        kb_version: The KB version that the caller names; None means the loaded one.
        intent_override: The intent that staff chose or confirmed; None when none.
    """

    message: str
    as_of: datetime
    order_facts: OrderFacts | None = None
    kb_version: str | None = None
    intent_override: IntentName | None = None
