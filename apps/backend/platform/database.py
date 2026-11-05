from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone, timedelta
import hashlib
import json
import uuid

from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from .models import AuditEntry, Base, IdempotencyRecord


def utcnow():
    return datetime.now(timezone.utc)


class Problem(Exception):
    def __init__(self, status: int, code: str, detail: str):
        self.status, self.code, self.detail = status, code, detail


class Database:
    def __init__(self, engine):
        self.engine = engine

    @contextmanager
    def transaction(self):
        with Session(self.engine, expire_on_commit=False) as session, session.begin():
            yield session

    def create_schema(self, connection=None):
        with (self.engine.begin() if connection is None else nullcontext(connection)) as connection:
            Base.metadata.create_all(connection)
            connection.execute(text("CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1001"))
            connection.execute(text("""
                CREATE OR REPLACE FUNCTION protect_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'Append-only record'; END $$
            """))
            for table in ("audit_log_entries", "customer_messages"):
                connection.execute(text(f"DROP TRIGGER IF EXISTS immutable_record ON {table}"))
                connection.execute(text(f"CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION protect_audit()"))
            connection.execute(text("""
                CREATE OR REPLACE FUNCTION protect_authority() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF OLD.is_authority_required AND NOT NEW.is_authority_required THEN
                        RAISE EXCEPTION 'Authority cannot be cleared';
                    END IF;
                    RETURN NEW;
                END $$
            """))
            connection.execute(text("DROP TRIGGER IF EXISTS sticky_authority ON tickets"))
            connection.execute(text("CREATE TRIGGER sticky_authority BEFORE UPDATE ON tickets FOR EACH ROW EXECUTE FUNCTION protect_authority()"))
            connection.execute(text("""
                CREATE OR REPLACE FUNCTION protect_account_role() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF OLD.role <> NEW.role AND NOT (OLD.role IN ('staff','manager') AND NEW.role IN ('staff','manager')) THEN
                        RAISE EXCEPTION 'Only staff/manager changes are allowed';
                    END IF;
                    RETURN NEW;
                END $$
            """))
            connection.execute(text("DROP TRIGGER IF EXISTS restricted_role ON accounts"))
            connection.execute(text("CREATE TRIGGER restricted_role BEFORE UPDATE ON accounts FOR EACH ROW EXECUTE FUNCTION protect_account_role()"))


def audit(session, event, actor, trace_id, ticket_id=None, **data):
    session.add(AuditEntry(entry_id=str(uuid.uuid4()), occurred_at=utcnow(), event_type=event,
                           actor_account_id=actor, ticket_id=ticket_id, trace_id=trace_id, data=data))


def idempotent(session, account_id, operation, key, body, execute):
    if not key or len(key) > 200:
        raise Problem(422, "invalid-request", "A valid Idempotency-Key is required.")
    record_id = hashlib.sha256(f"{account_id}:{operation}:{key}".encode()).hexdigest()
    # One transaction-scoped lock covers the lookup, write and stored response across replicas.
    lock_id = int(record_id[:15], 16)
    session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    existing = session.get(IdempotencyRecord, record_id)
    if existing:
        if existing.request_hash != fingerprint:
            raise Problem(409, "idempotency-key-reused", "This action key was already used with different content.")
        return existing.response
    result = execute()
    session.add(IdempotencyRecord(record_id=record_id, request_hash=fingerprint, response=result, created_at=utcnow()))
    session.execute(delete(IdempotencyRecord).where(IdempotencyRecord.created_at < utcnow() - timedelta(days=1)))
    return result
