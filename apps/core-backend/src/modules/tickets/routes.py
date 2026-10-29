from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.db import get_db_session
from src.contracts import AccessScope
from src.errors import AppError
from src.idempotency import parse_if_match
from src.crypto import decrypt_text
from src.modules.auth.routes import get_current_user_scope
from src.modules.auth.service import authorize
from src.modules.tickets.models import TicketModel, MessageModel
from src.modules.tickets.schemas import (
    CreateTicketRequest,
    CreateMessageRequest,
    UpdateTicketRequest,
)
from src.modules.tickets.service import (
    get_ticket_for_actor,
    create_ticket,
    add_message,
    clear_current_decision_and_bump_version,
)

router = APIRouter(prefix="/api/v1/tickets", tags=["tickets"])

def serialize_ticket(ticket: TicketModel, role: str) -> dict:
    if role == "customer":
        return {
            "id": ticket.id,
            "customer_id": ticket.customer_id,
            "order_id": ticket.order_id,
            "status": ticket.status,
            "priority": ticket.priority,
            "version": ticket.version,
            "created_at": ticket.created_at.isoformat(),
            "updated_at": ticket.updated_at.isoformat(),
        }
    # Staff view (agent, manager)
    return {
        "id": ticket.id,
        "customer_id": ticket.customer_id,
        "order_id": ticket.order_id,
        "assigned_agent_id": ticket.assigned_agent_id,
        "handling_queue": ticket.handling_queue,
        "status": ticket.status,
        "priority": ticket.priority,
        "context_version": ticket.context_version,
        "version": ticket.version,
        "current_run_id": ticket.current_run_id,
        "current_decision_id": ticket.current_decision_id,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
    }

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_new_ticket(
    payload: CreateTicketRequest,
    response: Response,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    ticket = await create_ticket(db, scope, payload)
    response.headers["ETag"] = f'"{ticket.version}"'
    return {"data": serialize_ticket(ticket, scope.role)}

@router.get("")
async def list_tickets(
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    if scope.role == "admin":
        raise AppError(status=403, code="forbidden", title="Forbidden", detail="Admin is forbidden from reading tickets.")

    stmt = select(TicketModel).order_by(TicketModel.updated_at.desc(), TicketModel.id.desc())
    if scope.role == "customer":
        stmt = stmt.where(TicketModel.customer_id == str(scope.actor_id))
    elif scope.role == "agent":
        stmt = stmt.where(
            (TicketModel.assigned_agent_id == str(scope.actor_id)) |
            (TicketModel.assigned_agent_id.is_(None) & (TicketModel.handling_queue == "standard"))
        )

    result = await db.execute(stmt)
    tickets = result.scalars().all()
    return {"data": [serialize_ticket(t, scope.role) for t in tickets]}

@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: UUID,
    response: Response,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    ticket = await get_ticket_for_actor(db, ticket_id, scope)
    response.headers["ETag"] = f'"{ticket.version}"'
    return {"data": serialize_ticket(ticket, scope.role)}

@router.patch("/{ticket_id}")
async def update_ticket(
    ticket_id: UUID,
    payload: UpdateTicketRequest,
    response: Response,
    if_match: str | None = Header(None, alias="If-Match"),
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    ticket = await get_ticket_for_actor(db, ticket_id, scope, for_update=True)
    parse_if_match(if_match, ticket.version)

    if payload.status is not None:
        ticket.status = payload.status
    if payload.assigned_agent_id is not None:
        ticket.assigned_agent_id = str(payload.assigned_agent_id)
    if payload.handling_queue is not None:
        ticket.handling_queue = payload.handling_queue

    ticket.version += 1
    await db.commit()
    await db.refresh(ticket)

    response.headers["ETag"] = f'"{ticket.version}"'
    return {"data": serialize_ticket(ticket, scope.role)}

@router.get("/{ticket_id}/messages")
async def get_ticket_messages(
    ticket_id: UUID,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    ticket = await get_ticket_for_actor(db, ticket_id, scope)
    stmt = select(MessageModel).where(MessageModel.ticket_id == str(ticket.id)).order_by(MessageModel.created_at)
    res = await db.execute(stmt)
    messages = res.scalars().all()
    decrypted_msgs = []
    for m in messages:
        txt = decrypt_text(m.content_ciphertext)
        decrypted_msgs.append({
            "id": m.id,
            "ticket_id": m.ticket_id,
            "sender_id": m.sender_id,
            "sender_role": m.sender_role,
            "direction": "inbound" if m.sender_role == "customer" else "outbound",
            "body": txt,
            "content": txt,
            "created_at": m.created_at.isoformat(),
        })
    return {"data": decrypted_msgs}

@router.post("/{ticket_id}/messages", status_code=status.HTTP_201_CREATED)
async def post_ticket_message(
    ticket_id: UUID,
    payload: CreateMessageRequest,
    scope: AccessScope = Depends(get_current_user_scope),
    db: AsyncSession = Depends(get_db_session),
):
    msg = await add_message(db, ticket_id, scope, payload.message)
    return {
        "data": {
            "id": msg.id,
            "ticket_id": msg.ticket_id,
            "sender_id": msg.sender_id,
            "sender_role": msg.sender_role,
            "content": payload.message,
            "created_at": msg.created_at.isoformat(),
        }
    }
