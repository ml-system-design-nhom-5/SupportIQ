"""Builders of tickets with their customer message (TEST-05)."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import insert

from supportiq_backend.tickets.adapters.tables import CustomerMessageRow, TicketRow
from tests.integration.builders.rows import RowWriter


@dataclass(frozen=True, slots=True)
class TicketSpec:
    """A ticket to build, with its customer message.

    Attributes:
        message: The customer message.
        status: The ticket state.
        source: `shop` or `import`.
        is_authority_required: The authority flag.
        created_at: When it was created; the next time of the builder when None.
        handling_mode: `assisted` or `manual`.
        handling_started_at: Its first view, if any.
        closed_at: When its reply was sent, if it was.
        study_pair_id: Its study pair, if any.
        study_batch: Its study batch, if any.
    """

    message: str = "Where is my parcel?"
    status: str = "open"
    source: str = "shop"
    is_authority_required: bool = False
    created_at: datetime | None = None
    handling_mode: str = "assisted"
    handling_started_at: datetime | None = None
    closed_at: datetime | None = None
    study_pair_id: str | None = None
    study_batch: str | None = None


class TicketRows:
    """Insert tickets."""

    def __init__(self, writer: RowWriter) -> None:
        """Keep the writer that every area shares.

        Args:
            writer: Writes the rows and gives their deterministic values.
        """
        self._writer = writer

    async def ticket(self, customer_id: UUID, order_id: str | None, spec: TicketSpec) -> str:
        """Insert a ticket with its customer message and return the ticket ID."""
        moment = spec.created_at or self._writer.next_time()
        async with self._writer.begin() as connection:
            ticket_id = await connection.scalar(
                insert(TicketRow)
                .values(
                    customer_id=customer_id,
                    order_id=order_id,
                    status=spec.status,
                    handling_mode=spec.handling_mode,
                    is_authority_required=spec.is_authority_required,
                    source=spec.source,
                    created_at=moment,
                    handling_started_at=spec.handling_started_at,
                    closed_at=spec.closed_at,
                    study_pair_id=spec.study_pair_id,
                    study_batch=spec.study_batch,
                )
                .returning(TicketRow.ticket_id)
            )
            await connection.execute(
                insert(CustomerMessageRow).values(
                    message_id=self._writer.next_uuid(),
                    ticket_id=ticket_id,
                    body=spec.message,
                    created_at=moment,
                )
            )
        return str(ticket_id)
