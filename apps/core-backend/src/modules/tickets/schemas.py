from uuid import UUID
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict

HandlingQueue = Literal["standard", "manager"]
TicketStatus = Literal["open", "resolved", "closed"]

class CreateTicketRequest(BaseModel):
    message: str
    order_id: UUID | None = None
    priority: str = "normal"

class CreateMessageRequest(BaseModel):
    message: str

class UpdateTicketRequest(BaseModel):
    status: TicketStatus | None = None
    assigned_agent_id: UUID | None = None
    handling_queue: HandlingQueue | None = None

class TicketCustomerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    order_id: UUID | None = None
    status: str
    priority: str
    version: int
    created_at: datetime
    updated_at: datetime

class TicketStaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    customer_id: UUID
    order_id: UUID | None = None
    assigned_agent_id: UUID | None = None
    handling_queue: str
    status: str
    priority: str
    context_version: int
    version: int
    current_run_id: UUID | None = None
    current_decision_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

class MessageResponse(BaseModel):
    id: UUID
    ticket_id: UUID
    sender_id: UUID
    sender_role: str
    content: str
    created_at: datetime
