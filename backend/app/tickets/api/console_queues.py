"""The query parameters and the page of `listConsoleTickets`, the console's queues.

A cursor holds the queue, the time that orders the queue, and the last ticket ID (CON-14), so
a cursor of one queue is refused by another.
"""

from pydantic import MISSING

from app.accounts import OperationId
from app.generated import Cursor
from app.generated import TicketSummaryPage as ContractTicketSummaryPage
from app.platform import InvalidCursorError, InvalidRequestError
from app.platform.web import decode_cursor, encode_cursor, format_timestamp
from app.tickets.api.console_views import to_ticket_summary
from app.tickets.domain import (
    ConsoleTicketPosition,
    TicketId,
    TicketStatus,
    TicketSummaryPage,
)

LIST_OPERATION = OperationId.LIST_CONSOLE_TICKETS.value
CURSOR_STATUS_FIELD = "status"
CURSOR_MOMENT_FIELD = "moment"
CURSOR_TICKET_FIELD = "ticket_id"


class InvalidStatusFilterError(InvalidRequestError):
    """The `status` parameter of `listConsoleTickets` is missing or unknown (422)."""

    def __init__(self) -> None:
        """Build the error with the detail of its contract example."""
        super().__init__(
            "The parameter status must be open, awaiting_approval, escalated, or closed."
        )


def parse_status_filter(raw: str | None) -> TicketStatus:
    """Read the required `status` parameter of `listConsoleTickets`.

    Args:
        raw: The parameter as sent, or None when absent.

    Returns:
        The queue.

    Raises:
        InvalidStatusFilterError: The parameter is missing or unknown.
    """
    try:
        return TicketStatus(raw)
    except ValueError as error:
        raise InvalidStatusFilterError from error


def parse_console_cursor(raw: str | None, status: TicketStatus) -> ConsoleTicketPosition | None:
    """Read the cursor of `listConsoleTickets`: the last ticket of the previous page.

    Args:
        raw: The `cursor` query parameter, or None when absent.
        status: The queue of this request; a cursor of another queue is refused.

    Returns:
        The position, or None for the first page.

    Raises:
        InvalidCursorError: The cursor is malformed, from another operation, or another queue.
    """
    fields = decode_cursor(
        raw,
        LIST_OPERATION,
        frozenset({CURSOR_STATUS_FIELD, CURSOR_MOMENT_FIELD, CURSOR_TICKET_FIELD}),
    )
    if fields is None:
        return None
    if fields.text(CURSOR_STATUS_FIELD) != status.value:
        raise InvalidCursorError
    return ConsoleTicketPosition(
        status, fields.timestamp(CURSOR_MOMENT_FIELD), TicketId(fields.text(CURSOR_TICKET_FIELD))
    )


def to_summary_page(page: TicketSummaryPage) -> ContractTicketSummaryPage:
    """Map a page of a queue to the contract.

    Args:
        page: The page.

    Returns:
        The contract model; `next_cursor` is absent on the last page.
    """
    position = page.next_position
    next_cursor: Cursor | MISSING = MISSING
    if position is not None:
        next_cursor = Cursor(
            encode_cursor(
                LIST_OPERATION,
                {
                    CURSOR_STATUS_FIELD: position.status.value,
                    CURSOR_MOMENT_FIELD: format_timestamp(position.moment),
                    CURSOR_TICKET_FIELD: position.ticket_id,
                },
            )
        )
    return ContractTicketSummaryPage(
        items=[to_ticket_summary(summary) for summary in page.items], next_cursor=next_cursor
    )
