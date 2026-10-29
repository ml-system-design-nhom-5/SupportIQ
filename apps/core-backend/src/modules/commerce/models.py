from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.db import Base
from src.config import settings

schema_arg = {"schema": "app"} if not settings.app_db_url.startswith("sqlite") else {}

class ProductModel(Base):
    __tablename__ = "products"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    sku = Column(String(100), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(String(1000), nullable=True)
    unit_price_minor = Column(BigInteger, nullable=False)
    currency = Column(String(10), nullable=False, default="VND")
    stock_quantity = Column(Integer, nullable=False, default=0)
    category = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

class OrderModel(Base):
    __tablename__ = "orders"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    customer_id = Column(String(36), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="placed")
    total_minor = Column(BigInteger, nullable=False)
    currency = Column(String(10), nullable=False, default="VND")
    demo = Column(Boolean, nullable=False, default=True)
    shipping_address = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    items = relationship("OrderItemModel", back_populates="order", cascade="all, delete-orphan")
    shipment = relationship("ShipmentModel", back_populates="order", uselist=False, cascade="all, delete-orphan")
    refund = relationship("RefundModel", back_populates="order", uselist=False, cascade="all, delete-orphan")

class OrderItemModel(Base):
    __tablename__ = "order_items"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}products.id"), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit_price_minor = Column(BigInteger, nullable=False)
    total_minor = Column(BigInteger, nullable=False)

    order = relationship("OrderModel", back_populates="items")
    product = relationship("ProductModel")

class ShipmentModel(Base):
    __tablename__ = "shipments"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}orders.id", ondelete="CASCADE"), nullable=False)
    tracking_code = Column(String(100), nullable=True)
    carrier = Column(String(100), nullable=True)
    status = Column(String(50), nullable=False, default="in_transit")
    estimated_delivery = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    order = relationship("OrderModel", back_populates="shipment")

class RefundModel(Base):
    __tablename__ = "refunds"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}orders.id", ondelete="CASCADE"), nullable=False)
    amount_minor = Column(BigInteger, nullable=False)
    reason = Column(String(500), nullable=True)
    status = Column(String(50), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    order = relationship("OrderModel", back_populates="refund")
