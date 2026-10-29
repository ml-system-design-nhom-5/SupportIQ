from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, LargeBinary, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from src.db import Base
from src.config import settings

schema_arg = {"schema": "app"} if not settings.app_db_url.startswith("sqlite") else {}

class TicketModel(Base):
    __tablename__ = "tickets"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    customer_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}users.id"), nullable=False, index=True)
    order_id = Column(String(36), nullable=True)
    assigned_agent_id = Column(String(36), nullable=True)
    handling_queue = Column(String(50), nullable=False, default="standard")
    status = Column(String(50), nullable=False, default="open")
    priority = Column(String(50), nullable=False, default="normal")
    context_version = Column(Integer, nullable=False, default=1)
    version = Column(Integer, nullable=False, default=1)
    current_run_id = Column(String(36), nullable=True)
    current_decision_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    messages = relationship("MessageModel", back_populates="ticket", cascade="all, delete-orphan", order_by="MessageModel.created_at")

class MessageModel(Base):
    __tablename__ = "messages"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(String(36), nullable=False)
    sender_role = Column(String(32), nullable=False)
    content_ciphertext = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    ticket = relationship("TicketModel", back_populates="messages")
