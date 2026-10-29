from typing import Literal, Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict

Role = Literal["customer", "agent", "manager", "admin"]
HandlingQueue = Literal["standard", "manager"]
TicketStatus = Literal["open", "resolved", "closed"]

class AccessScope(BaseModel):
    model_config = ConfigDict(frozen=True)
    actor_id: UUID
    role: Role
    role_version: int
    session_id: UUID

class AuditEventInput(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_type: str
    request_id: UUID
    ticket_id: UUID | None = None
    run_id: UUID | None = None
    actor_id: UUID | None = None
    details: dict[str, Any] = {}

class TicketContextRef(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticket_id: UUID
    customer_id: UUID
    order_id: UUID | None = None
    context_version: int
    version: int
    handling_queue: HandlingQueue
    status: TicketStatus
