from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.config import settings
from src.contracts import AccessScope
from src.errors import AppError
from src.crypto import encrypt_text, decrypt_text
from src.modules.commerce.models import OrderModel
from src.modules.tickets.models import TicketModel, MessageModel
from src.modules.tickets.schemas import CreateTicketRequest, UpdateTicketRequest

async def get_ticket_for_actor(
    session: AsyncSession,
    ticket_id: UUID,
    scope: AccessScope,
    for_update: bool = False,
) -> TicketModel:
    if scope.role == "admin":
        raise AppError(
            status=403,
            code="forbidden",
            title="Forbidden",
            detail="Admin role is strictly forbidden from accessing ticket content.",
        )

    stmt = select(TicketModel).where(TicketModel.id == str(ticket_id))
    if for_update and not settings.app_db_url.startswith("sqlite"):
        stmt = stmt.with_for_update()

    result = await session.execute(stmt)
    ticket = result.scalar_one_or_none()

    if not ticket:
        raise AppError(status=404, code="not_found", title="Not Found", detail="Ticket not found.")

    if scope.role == "customer" and ticket.customer_id != str(scope.actor_id):
        raise AppError(status=404, code="not_found", title="Not Found", detail="Ticket not found.")

    return ticket

def clear_current_decision_and_bump_version(
    session: AsyncSession,
    ticket: TicketModel,
    bump_context: bool = False,
) -> None:
    ticket.current_decision_id = None
    ticket.version += 1
    if bump_context:
        ticket.context_version += 1
    ticket.updated_at = datetime.now(timezone.utc)

async def create_ticket(
    session: AsyncSession,
    scope: AccessScope,
    payload: CreateTicketRequest,
) -> TicketModel:
    if scope.role != "customer":
        raise AppError(status=403, code="forbidden", title="Forbidden", detail="Only customers can initiate tickets.")

    if payload.order_id is not None:
        # Check order ownership
        order_stmt = select(OrderModel).where(
            OrderModel.id == str(payload.order_id),
            OrderModel.customer_id == str(scope.actor_id),
        )
        order_res = await session.execute(order_stmt)
        if not order_res.scalar_one_or_none():
            raise AppError(status=404, code="not_found", title="Not Found", detail="Order not found for this customer.")

    ticket_id = uuid4()
    now = datetime.now(timezone.utc)
    ticket = TicketModel(
        id=str(ticket_id),
        customer_id=str(scope.actor_id),
        order_id=str(payload.order_id) if payload.order_id else None,
        handling_queue="standard",
        status="open",
        priority=payload.priority,
        context_version=1,
        version=1,
        current_run_id=None,
        current_decision_id=None,
        created_at=now,
        updated_at=now,
    )
    session.add(ticket)

    msg = MessageModel(
        id=str(uuid4()),
        ticket_id=str(ticket_id),
        sender_id=str(scope.actor_id),
        sender_role="customer",
        content_ciphertext=encrypt_text(payload.message),
        created_at=now,
    )
    session.add(msg)
    await session.commit()
    await session.refresh(ticket)
    return ticket

async def add_message(
    session: AsyncSession,
    ticket_id: UUID,
    scope: AccessScope,
    message_text: str,
) -> MessageModel:
    ticket = await get_ticket_for_actor(session, ticket_id, scope, for_update=True)

    if ticket.status == "closed":
        raise AppError(status=409, code="state_conflict", title="Conflict", detail="Cannot add message to closed ticket.")

    bump_context = False
    if scope.role == "customer" and ticket.status == "resolved":
        ticket.status = "open"
        bump_context = True

    clear_current_decision_and_bump_version(session, ticket, bump_context=bump_context)

    now = datetime.now(timezone.utc)
    msg = MessageModel(
        id=str(uuid4()),
        ticket_id=str(ticket.id),
        sender_id=str(scope.actor_id),
        sender_role=scope.role,
        content_ciphertext=encrypt_text(message_text),
        created_at=now,
    )
    session.add(msg)
    await session.commit()
    return msg
