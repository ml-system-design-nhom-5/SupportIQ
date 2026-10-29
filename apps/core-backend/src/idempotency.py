import hmac
import hashlib
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from sqlalchemy import Column, String, Integer, DateTime, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import Base
from src.errors import AppError
from src.config import settings

class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = {"schema": "app"} if not settings.app_db_url.startswith("sqlite") else {}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    actor_id = Column(String(36), nullable=False)
    method = Column(String(10), nullable=False)
    route = Column(String(255), nullable=False)
    key = Column(String(255), nullable=False)
    request_hmac = Column(String(64), nullable=False)
    resource_id = Column(String(36), nullable=True)
    response_status = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    response_headers = Column(JSON, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

def calculate_request_hmac(body: bytes) -> str:
    key_bytes = settings.app_encryption_key.encode("utf-8")
    return hmac.new(key_bytes, body, hashlib.sha256).hexdigest()

def parse_if_match(if_match_header: str | None, current_version: int) -> None:
    if if_match_header is None or not if_match_header.strip():
        raise AppError(
            status=428,
            code="precondition_required",
            title="Precondition Required",
            detail="If-Match header is required for this operation."
        )
    header_val = if_match_header.strip()
    expected_quoted = f'"{current_version}"'
    expected_raw = str(current_version)
    if header_val != expected_quoted and header_val != expected_raw:
        raise AppError(
            status=412,
            code="version_conflict",
            title="Version Conflict",
            detail=f"Target version mismatch. Expected {expected_quoted}, got {header_val}."
        )

async def check_or_store_idempotency(
    session: AsyncSession,
    actor_id: UUID,
    method: str,
    route: str,
    key: str,
    canonical_body: bytes,
    ttl_minutes: int = 1440,
) -> IdempotencyRecord | None:
    body_hmac = calculate_request_hmac(canonical_body)
    stmt = select(IdempotencyRecord).where(
        IdempotencyRecord.actor_id == str(actor_id),
        IdempotencyRecord.method == method.upper(),
        IdempotencyRecord.route == route,
        IdempotencyRecord.key == key,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing is not None:
        if existing.request_hmac != body_hmac:
            raise AppError(
                status=409,
                code="idempotency_conflict",
                title="Idempotency Conflict",
                detail="Payload does not match original request for this Idempotency-Key."
            )
        return existing

    record = IdempotencyRecord(
        id=str(uuid4()),
        actor_id=str(actor_id),
        method=method.upper(),
        route=route,
        key=key,
        request_hmac=body_hmac,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes),
    )
    session.add(record)
    await session.flush()
    return None
