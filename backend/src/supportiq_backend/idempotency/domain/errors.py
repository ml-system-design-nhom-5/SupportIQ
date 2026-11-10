"""Errors of idempotent writes (ERR-15, contract `IdempotencyKeyReused`)."""

from typing import ClassVar

from supportiq_backend.platform import (
    BackendError,
    ErrorCode,
    InvalidRequestError,
    UnexpectedFailureError,
)


class IdempotencyKeyReusedError(BackendError):
    """The key was used before by the same account on the same operation in another request."""

    code: ClassVar[ErrorCode] = ErrorCode.IDEMPOTENCY_KEY_REUSED

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The Idempotency-Key was already used with a different request.")


class InvalidIdempotencyKeyError(InvalidRequestError):
    """The `Idempotency-Key` header is absent or is not a lowercase UUID (contract, 422)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The header Idempotency-Key is missing or is not a lowercase UUID.")


class IdempotencyRecordIncompleteError(UnexpectedFailureError):
    """A committed idempotency record has no response, which no write ever commits."""
