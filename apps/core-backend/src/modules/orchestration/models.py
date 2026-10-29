from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, Integer, BigInteger, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from src.db import Base
from src.config import settings

schema_arg = {"schema": "app"} if not settings.app_db_url.startswith("sqlite") else {}

class ReleaseManifestModel(Base):
    __tablename__ = "release_manifests"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    release_tag = Column(String(100), unique=True, nullable=False)
    intent_model_name = Column(String(100), nullable=False)
    intent_model_version = Column(String(50), nullable=False)
    embedding_model_name = Column(String(100), nullable=False)
    embedding_model_version = Column(String(50), nullable=False)
    llm_model_name = Column(String(100), nullable=False)
    prompt_template_hash = Column(String(64), nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

class PipelineRunModel(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    ticket_id = Column(String(36), nullable=False, index=True)
    customer_id = Column(String(36), nullable=False)
    status = Column(String(50), nullable=False, default="queued", index=True)
    stage = Column(String(50), nullable=False, default="pipeline")
    reason_codes = Column(JSON, nullable=False, default=list)
    deadline_at = Column(DateTime(timezone=True), nullable=False)
    cost_status = Column(String(50), nullable=False, default="none")
    cost_micro = Column(BigInteger, nullable=True)
    draft_id = Column(String(36), nullable=True)
    release_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    jobs = relationship("JobModel", back_populates="run", cascade="all, delete-orphan", lazy="selectin")
    attempts = relationship("LlmAttemptModel", back_populates="run", cascade="all, delete-orphan", lazy="selectin")
    draft = relationship("DraftModel", back_populates="run", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    evidence = relationship("EvidenceSnapshotModel", back_populates="run", cascade="all, delete-orphan", lazy="selectin")

class JobModel(Base):
    __tablename__ = "jobs"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(String(50), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued")
    worker_id = Column(String(100), nullable=True)
    lease_token = Column(String(36), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("PipelineRunModel", back_populates="jobs")

class LlmAttemptModel(Base):
    __tablename__ = "llm_attempts"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    attempt_no = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="in_flight")
    cost_micro = Column(BigInteger, nullable=True)
    response_tokens = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("PipelineRunModel", back_populates="attempts")

class EvidenceSnapshotModel(Base):
    __tablename__ = "evidence_snapshots"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}pipeline_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    citation_id = Column(String(100), nullable=False)
    source_id = Column(String(100), nullable=False)
    snippet = Column(String(2000), nullable=False)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("PipelineRunModel", back_populates="evidence")

class DraftModel(Base):
    __tablename__ = "drafts"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), ForeignKey(f"{'app.' if schema_arg else ''}pipeline_runs.id", ondelete="CASCADE"), unique=True, nullable=False)
    draft_body = Column(String(5000), nullable=False)
    citation_ids = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("PipelineRunModel", back_populates="draft")
