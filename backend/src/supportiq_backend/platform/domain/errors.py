"""The root error of backend and the errors that several features share (PY-20, ERR-01)."""

from collections.abc import Mapping
from enum import StrEnum
from typing import ClassVar


class ErrorCode(StrEnum):
    """The problem type of an error, by its name in the contract's registry (CON-12)."""

    INVALID_REQUEST = "invalid-request"
    UNAUTHENTICATED = "unauthenticated"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not-found"
    IDEMPOTENCY_KEY_REUSED = "idempotency-key-reused"
    LOGIN_NAME_TAKEN = "login-name-taken"
    NOT_READY = "not-ready"
    INTERNAL_ERROR = "internal-error"


class BackendError(Exception):
    """The root of every error that backend raises on purpose (PY-20).

    Each subclass fixes its `code`, which decides the HTTP status and the problem type in the
    single exception handler (ERR-03). Each subclass also builds its own `detail` from safe
    values only (PY-23, ERR-02): never message text, a display name, an order ID, or a secret.
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
            The extension members by name. Empty for most errors.
        """
        return {}


class DatabaseUnavailableError(BackendError):
    """The database cannot serve the request now: unreachable, or a timeout fired (ERR-09).

    The request changed nothing, and the client may retry it (contract `NotReady`).
    """

    code: ClassVar[ErrorCode] = ErrorCode.NOT_READY

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The database is not available.")


class UnexpectedFailureError(BackendError):
    """A defect: a broken invariant or an exception that no code expected (ERR taxonomy)."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self) -> None:
        """Build the error with its fixed detail, which names no internal detail (CON-12)."""
        super().__init__("An unexpected error occurred.")


class DatabaseOperationError(UnexpectedFailureError):
    """The database refused an operation that backend never sends on purpose: a defect."""


class ResourceNotFoundError(BackendError):
    """The resource does not exist, or the caller may not know about it (SEC-17).

    Every not-found error of every feature has this one detail, so a resource of another
    customer and an unknown ID give the same body.
    """

    code: ClassVar[ErrorCode] = ErrorCode.NOT_FOUND

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The resource was not found.")


class InvalidRequestError(BackendError):
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


class InvalidLimitError(InvalidRequestError):
    """The `limit` parameter is not an integer in the documented range (CON-14)."""

    def __init__(self, minimum: int, maximum: int) -> None:
        """Build the error from the documented range.

        Args:
            minimum: The smallest allowed page size.
            maximum: The largest allowed page size.
        """
        super().__init__(f"The parameter limit must be an integer from {minimum} to {maximum}.")


class InvalidCursorError(InvalidRequestError):
    """The `cursor` parameter is malformed, empty, or was returned by another operation."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The parameter cursor is not a cursor of this operation.")


class InvalidParameterError(InvalidRequestError):
    """A query parameter other than `limit` and `cursor` is not valid."""

    def __init__(self, name: str) -> None:
        """Build the error from the parameter name.

        Args:
            name: The name of the parameter, never its value.
        """
        super().__init__(f"The parameter {name} is not valid.")
