"""The root error of ai-service and the errors that several features share (PY-20, ERR-01)."""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar


class ErrorCode(StrEnum):
    """The problem type of an error, by its name in the contract's registry (CON-12).

    These are the problem types that contract 1.0.0 of ai-service uses.
    """

    INVALID_REQUEST = "invalid-request"
    UNAUTHENTICATED = "unauthenticated"
    NOT_FOUND = "not-found"
    NOT_READY = "not-ready"
    INTERNAL_ERROR = "internal-error"


class AiServiceError(Exception):
    """The root of every error that ai-service raises on purpose (PY-20).

    Each subclass fixes its `code`, which decides the HTTP status and the problem type in the
    single exception handler (ERR-03). Each subclass also builds its own `detail` from safe
    values only (PY-23, ERR-02): never message text, a placeholder, or a secret.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, detail: str) -> None:
        """Keep the safe detail of the error.

        Args:
            detail: An English sentence for developers, with no confidential value.
        """
        super().__init__(detail)
        self.detail = detail

    def problem_extensions(self) -> Mapping[str, str]:
        """Return the Problem Details extension members of this error, other than `trace_id`.

        Returns:
            The extension members by name. Empty for every error of contract 1.0.0.
        """
        return {}


class UnexpectedFailureError(AiServiceError):
    """A defect: a broken invariant or an exception that no code expected (ERR taxonomy)."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self) -> None:
        """Build the error with its fixed detail, which names no internal detail (CON-12)."""
        super().__init__("An unexpected error occurred.")


class ResourceNotFoundError(AiServiceError):
    """The resource does not exist, such as a KB document version that the KB lacks."""

    code: ClassVar[ErrorCode] = ErrorCode.NOT_FOUND

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The resource was not found.")


class ServiceTokenRejectedError(AiServiceError):
    """The request has no `Authorization` header, or its bearer token is not the service token.

    The detail never repeats the token that was sent (SEC-09).
    """

    code: ClassVar[ErrorCode] = ErrorCode.UNAUTHENTICATED

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The request has no valid service token.")


class InvalidRequestError(AiServiceError):
    """The request breaks the contract: a body, header, or parameter is not valid (CON-11)."""

    code: ClassVar[ErrorCode] = ErrorCode.INVALID_REQUEST


class RequestContractError(InvalidRequestError):
    """The request does not match the contract at one or more locations."""

    def __init__(self, locations: tuple[str, ...]) -> None:
        """Build the error from the locations that failed validation.

        Args:
            locations: Where the request is invalid, such as `body.message`. Names only,
                never the values that were sent.
        """
        super().__init__(
            "The request does not match the contract at: " + ", ".join(locations) + "."
        )
        self.locations = locations
