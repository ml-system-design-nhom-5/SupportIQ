"""The commerce records that support reads about one customer (backend ticket workflow design).

Every value here is Confidential except the identifiers that the backend foundation design
marks Internal, so no class has a generated `repr` and no value reaches a log, a trace, or an
error (LOG-29). Only `backend` reads them: pseudonymization for the known values of a ticket,
and the console for the ticket workspace.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from supportiq_backend.accounts import CustomerId
from supportiq_backend.commerce.domain.catalog import Order, OrderId


@dataclass(frozen=True, slots=True, repr=False)
class CustomerContact:
    """The personal values of a customer.

    Attributes:
        display_name: The name shown to staff.
        email: The synthetic email address.
        phone: The synthetic phone number.
    """

    display_name: str
    email: str
    phone: str


@dataclass(frozen=True, slots=True, repr=False)
class OrderReferences:
    """The values of an order that identify a person's purchase.

    Attributes:
        order_id: The order identifier.
        tracking_code: The tracking code of its shipment; absent without a shipment record.
        transaction_id: The payment transaction ID.
        shipping_address: The shipping address.
    """

    order_id: OrderId
    tracking_code: str | None
    transaction_id: str
    shipping_address: str


@dataclass(frozen=True, slots=True, repr=False)
class AddressedOrder:
    """An order with its shipping address, as only the console shows it.

    Attributes:
        order: The order as the shop shows it.
        shipping_address: The shipping address.
    """

    order: Order
    shipping_address: str


class CustomerRecords(Protocol):
    """Read the commerce records of one customer for support; it never writes (ADR-0013)."""

    async def load_contact(self, customer_id: CustomerId) -> CustomerContact | None:
        """Load the personal values of a customer.

        Args:
            customer_id: The customer.

        Returns:
            The values, or None when the customer is unknown.
        """
        ...

    async def load_order_references(
        self, customer_id: CustomerId, order_id: OrderId
    ) -> OrderReferences | None:
        """Load the identifying values of one of the customer's orders.

        Args:
            customer_id: The customer.
            order_id: The order.

        Returns:
            The values, or None when the order is unknown or another customer's.
        """
        ...

    async def load_display_names(
        self, customer_ids: frozenset[CustomerId]
    ) -> Mapping[CustomerId, str]:
        """Load the display names of several customers in one query.

        Args:
            customer_ids: The customers.

        Returns:
            The display name of each known customer.
        """
        ...

    async def load_addressed_orders(self, customer_id: CustomerId) -> tuple[AddressedOrder, ...]:
        """Load every order of a customer with its shipping address, newest first.

        Args:
            customer_id: The customer.

        Returns:
            The orders, by `placed_at` descending, then by order ID.
        """
        ...
