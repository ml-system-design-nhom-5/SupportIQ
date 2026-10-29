from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.db import Base
from src.config import settings

schema_arg = {"schema": "knowledge"} if not settings.app_db_url.startswith("sqlite") else {}
table_prefix = "knowledge_" if settings.app_db_url.startswith("sqlite") else ""

class KnowledgeDocumentModel(Base):
    __tablename__ = f"{table_prefix}documents"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title = Column(String(255), nullable=False)
    category = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    versions = relationship("KnowledgeDocumentVersionModel", back_populates="document", cascade="all, delete-orphan")

class KnowledgeDocumentVersionModel(Base):
    __tablename__ = f"{table_prefix}document_versions"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id = Column(
        String(36),
        ForeignKey(f"{'knowledge.' if schema_arg else table_prefix}documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False, default=1)
    policy_key = Column(String(100), nullable=False, index=True)
    normalized_rule_value = Column(String(255), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(50), nullable=False, default="draft", index=True)
    allowed_roles = Column(JSON, nullable=False, default=lambda: ["agent", "staff", "manager", "admin"])
    content_hash = Column(String(64), nullable=False)
    sanitized_excerpt = Column(String(5000), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    document = relationship("KnowledgeDocumentModel", back_populates="versions")
