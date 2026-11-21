"""ORM models of the commerce tables, used only inside the commerce adapters (PY-39).

The tables are seeded only: `supportiq_app` may read them and nothing else (ADR-0013). Order
IDs, tracking codes, transaction IDs, and everything about an order are Confidential;
products are Public.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class CommerceTables(DeclarativeBase):
    """The declarative base of the tables that commerce owns."""


class CustomerRow(CommerceTables):
    """A row of `customers`: a simulated shopper, all Confidential except the ID."""

    __tablename__ = "customers"

    customer_id: Mapped[UUID] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    phone: Mapped[str] = mapped_column(Text)


class ProductRow(CommerceTables):
    """A row of `products`, Public."""

    __tablename__ = "products"

    product_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(Text)
    price_amount_minor: Mapped[int] = mapped_column(BigInteger)
    price_currency: Mapped[str] = mapped_column(Text)


class OrderRow(CommerceTables):
    """A row of `orders`."""

    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(Text, primary_key=True)
    customer_id: Mapped[UUID]
    order_status: Mapped[str] = mapped_column(Text)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    order_total_amount_minor: Mapped[int] = mapped_column(BigInteger)
    order_total_currency: Mapped[str] = mapped_column(Text)
    shipping_cost_amount_minor: Mapped[int] = mapped_column(BigInteger)
    shipping_cost_currency: Mapped[str] = mapped_column(Text)
    shipping_address: Mapped[str] = mapped_column(Text)
    transaction_id: Mapped[str] = mapped_column(Text)


class OrderLineRow(CommerceTables):
    """A row of `order_lines`: a product appears at most once in an order."""

    __tablename__ = "order_lines"
    __table_args__ = (UniqueConstraint("order_id", "product_id"),)

    order_id: Mapped[str] = mapped_column(Text, primary_key=True)
    line_number: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[str] = mapped_column(Text)
    quantity: Mapped[int]


class ShipmentRow(CommerceTables):
    """A row of `shipments`: at most one per order."""

    __tablename__ = "shipments"

    shipment_id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(Text)
    shipment_status: Mapped[str] = mapped_column(Text)
    tracking_code: Mapped[str] = mapped_column(Text)
    estimated_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefundRow(CommerceTables):
    """A row of `refunds`: at most one per order."""

    __tablename__ = "refunds"

    refund_id: Mapped[UUID] = mapped_column(primary_key=True)
    order_id: Mapped[str] = mapped_column(Text)
    refund_status: Mapped[str] = mapped_column(Text)
    refund_amount_minor: Mapped[int] = mapped_column(BigInteger)
    refund_currency: Mapped[str] = mapped_column(Text)
    refund_requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
