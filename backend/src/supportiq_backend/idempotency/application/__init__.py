"""Application code of idempotency, used by every write use case (ERR-15)."""

from supportiq_backend.idempotency.application.guard import IdempotencyGuard

__all__ = ["IdempotencyGuard"]
