from uuid import UUID
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict

class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    event_type: str
    request_id: UUID
    ticket_id: UUID | None = None
    run_id: UUID | None = None
    actor_id: UUID | None = None
    details: dict[str, Any]
    occurred_at: datetime
