"""Errors of tickets (contract `NotFound`, SEC-17)."""

from app.platform import ResourceNotFoundError


class TicketNotFoundError(ResourceNotFoundError):
    """The ticket is unknown, imported, or another customer's: the same error for all three."""
