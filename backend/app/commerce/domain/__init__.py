"""Domain of commerce: products, orders, and the `CommerceGateway` port."""

from app.commerce.domain.catalog import (
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
from app.commerce.domain.errors import OrderNotFoundError, ProductNotFoundError
from app.commerce.domain.ports import CommerceGateway
from app.commerce.domain.support_records import (
    AddressedOrder,
    CustomerContact,
    CustomerRecords,
    OrderReferences,
)

__all__ = [
    "ORDER_ID_PATTERN",
    "PHONE_PATTERN",
    "TRACKING_CODE_PATTERN",
    "TRANSACTION_ID_PATTERN",
    "AddressedOrder",
    "CommerceGateway",
    "CustomerContact",
    "CustomerRecords",
    "Money",
    "Order",
    "OrderId",
    "OrderLine",
    "OrderNotFoundError",
    "OrderPage",
    "OrderReferences",
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
