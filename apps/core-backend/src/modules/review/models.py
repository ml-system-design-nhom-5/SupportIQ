from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from src.db import Base
from src.config import settings

schema_arg = {"schema": "app"} if not settings.app_db_url.startswith("sqlite") else {}

class ReviewDecisionModel(Base):
    __tablename__ = "review_decisions"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    actor_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}users.id"), nullable=False)
    source = Column(String(32), nullable=False)  # 'ai' | 'manual'
    action = Column(String(32), nullable=False)  # 'approve' | 'edit' | 'reject'
    draft_id = Column(String(36), nullable=True)
    body = Column(Text, nullable=True)
    reason = Column(String(500), nullable=True)
    order_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    reply = relationship("ReplyModel", back_populates="decision", uselist=False)

class ReplyModel(Base):
    __tablename__ = "replies"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}tickets.id", ondelete="CASCADE"), nullable=False, index=True)
    decision_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}review_decisions.id"), unique=True, nullable=False)
    actor_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}users.id"), nullable=False)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    decision = relationship("ReviewDecisionModel", back_populates="reply")
