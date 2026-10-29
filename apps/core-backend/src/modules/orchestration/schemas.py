from uuid import UUID
from datetime import datetime
from typing import Literal, Any
from pydantic import BaseModel, ConfigDict

class RunCreate(BaseModel):
    force: bool = False

class RunAccepted(BaseModel):
    id: UUID
    ticket_id: UUID
    status: str
    deadline_at: datetime

class RunDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    ticket_id: UUID
    customer_id: UUID
    status: str
    stage: str
    reason_codes: list[str] = []
    deadline_at: datetime
    cost_status: str
    cost_micro: int | None = None
    created_at: datetime
    updated_at: datetime

class ClaimedJob(BaseModel):
    job_id: UUID
    run_id: UUID
    stage: str
    lease_token: UUID
    payload: dict[str, Any] | None = None
