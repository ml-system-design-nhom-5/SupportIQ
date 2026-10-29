from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ProductResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    sku: str
    name: str
    description: str | None = None
    unit_price_minor: int
    currency: str
    stock_quantity: int
    category: str | None = None

class OrderItemInput(BaseModel):
    product_id: UUID
    quantity: int

class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    product_id: UUID
    quantity: int
    unit_price_minor: int
    total_minor: int

class CreateOrderRequest(BaseModel):
    items: list[OrderItemInput]
    shipping_address: dict | None = None

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    status: str
    total_minor: int
    currency: str
    demo: bool
    shipping_address: dict | None = None
    items: list[OrderItemResponse] = []
    created_at: datetime

class OrderSnapshotDTO(BaseModel):
    order_id: UUID
    customer_id: UUID
    status: str
    total_minor: int
    currency: str
    demo: bool
    items: list[OrderItemResponse]
    shipment_status: str | None = None
    tracking_code: str | None = None
    estimated_delivery: datetime | None = None
