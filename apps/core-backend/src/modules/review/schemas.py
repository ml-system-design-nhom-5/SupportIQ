from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

class DecisionCreate(BaseModel):
    source: Literal["ai", "manual"]
    action: Literal["approve", "edit", "reject"]
    draft_id: UUID | None = None
    body: str | None = None
    reason: str | None = None

class DecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ticket_id: UUID
    actor_id: UUID
    source: str
    action: str
    draft_id: UUID | None = None
    body: str | None = None
    reason: str | None = None
    order_version: int
    created_at: datetime

class ReplyCreate(BaseModel):
    decision_id: UUID

class ReplyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ticket_id: UUID
    decision_id: UUID
    actor_id: UUID
    body: str
    created_at: datetime
