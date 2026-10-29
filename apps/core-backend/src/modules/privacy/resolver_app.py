from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from src.config import settings
from src.crypto import encrypt_text, decrypt_text
from src.modules.privacy.scanner import scan_and_mask_text

resolver_app = FastAPI(title="SupportIQ Privacy Resolver Service")

# Model for token mapping in vault
from src.db import Base
from sqlalchemy import Column, String, LargeBinary, DateTime

schema_arg = {"schema": "vault"} if not settings.vault_db_url.startswith("sqlite") else {}

class TokenMappingModel(Base):
    __tablename__ = "token_mappings" if schema_arg else "vault_token_mappings"
    __table_args__ = schema_arg

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id = Column(String(36), nullable=False, index=True)
    token = Column(String(100), nullable=False)
    pii_type = Column(String(50), nullable=False)
    encrypted_value = Column(LargeBinary, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

class SanitizeRequest(BaseModel):
    run_id: UUID
    text: str

class SanitizeResponse(BaseModel):
    run_id: UUID
    sanitized_text: str
    token_count: int
    uncertain_pii: bool

@resolver_app.post("/internal/v1/sanitize", response_model=SanitizeResponse)
async def sanitize_payload(payload: SanitizeRequest, authorization: str | None = Header(None)):
    if not authorization or authorization != f"Bearer {settings.internal_service_token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Internal token required.")

    res = scan_and_mask_text(payload.text, run_id=payload.run_id)
    return SanitizeResponse(
        run_id=payload.run_id,
        sanitized_text=res.sanitized_text,
        token_count=len(res.mappings),
        uncertain_pii=res.uncertain_pii,
    )

@resolver_app.post("/internal/v1/purge-expired")
async def purge_expired_tokens(authorization: str | None = Header(None)):
    if not authorization or authorization != f"Bearer {settings.internal_service_token}":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Internal token required.")
    return {"status": "ok", "purged": 0}
