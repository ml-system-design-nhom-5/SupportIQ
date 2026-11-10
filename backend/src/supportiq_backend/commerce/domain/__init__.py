"""Domain of commerce: products, orders, and the `CommerceGateway` port."""

from supportiq_backend.commerce.domain.catalog import (
    ORDER_ID_PATTERN,
    PHONE_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
    Money,
    Order,
    OrderId,
    OrderLine,
    OrderPage,
    OrderStatus,
    Product,
    ProductId,
    ProductPage,
    ProductPosition,
    Refund,
    RefundStatus,
    Shipment,
    ShipmentStatus,
)
from supportiq_backend.commerce.domain.errors import OrderNotFoundError, ProductNotFoundError
from supportiq_backend.commerce.domain.ports import CommerceGateway

__all__ = [
    "ORDER_ID_PATTERN",
    "PHONE_PATTERN",
    "TRACKING_CODE_PATTERN",
    "TRANSACTION_ID_PATTERN",
    "CommerceGateway",
    "Money",
    "Order",
    "OrderId",
    "OrderLine",
    "OrderNotFoundError",
    "OrderPage",
    "OrderStatus",
    "Product",
    "ProductId",
    "ProductNotFoundError",
    "ProductPage",
    "ProductPosition",
    "Refund",
    "RefundStatus",
    "Shipment",
    "ShipmentStatus",
]
