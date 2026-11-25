"""Errors of the shop's commerce data (contract `NotFound`, SEC-17)."""

from app.platform import ResourceNotFoundError


class ProductNotFoundError(ResourceNotFoundError):
    """The product does not exist."""


class OrderNotFoundError(ResourceNotFoundError):
    """The order does not exist, or belongs to another customer: the same error for both."""
