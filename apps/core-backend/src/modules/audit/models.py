from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import Column, String, DateTime, JSON, event, DDL
from src.db import Base
from src.config import settings

schema_arg = {"schema": "audit"} if not settings.audit_writer_db_url.startswith("sqlite") else {}

class AuditEventModel(Base):
    __tablename__ = "events" if schema_arg else "audit_events"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_type = Column(String(100), nullable=False)
    request_id = Column(String(36), nullable=False)
    ticket_id = Column(String(36), nullable=True, index=True)
    run_id = Column(String(36), nullable=True)
    actor_id = Column(String(36), nullable=True)
    details = Column(JSON, nullable=False, default=dict)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)

# Attach SQLite trigger for testing environments
if settings.audit_writer_db_url.startswith("sqlite"):
    event.listen(
        AuditEventModel.__table__,
        "after_create",
        DDL("CREATE TRIGGER IF NOT EXISTS prevent_audit_delete BEFORE DELETE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;")
    )
    event.listen(
        AuditEventModel.__table__,
        "after_create",
        DDL("CREATE TRIGGER IF NOT EXISTS prevent_audit_update BEFORE UPDATE ON audit_events BEGIN SELECT RAISE(ABORT, 'audit.events is append-only'); END;")
    )
