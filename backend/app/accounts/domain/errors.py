"""Errors of authentication and authorization (ADR-0009, ADR-0012, contract responses)."""

from typing import ClassVar

from app.platform import BackendError, ErrorCode


class InvalidCredentialsError(BackendError):
    """The credentials were not accepted.

    One error for an unknown name, a wrong password, a deactivated account, and a throttled
    attempt, so the response never reveals which login names exist (ADR-0009, statement 8).
    """

    code: ClassVar[ErrorCode] = ErrorCode.UNAUTHENTICATED

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The login name or the password is not valid.")


class SessionRequiredError(BackendError):
    """The request has no valid session: missing, unknown, expired, idle, or deleted."""

    code: ClassVar[ErrorCode] = ErrorCode.UNAUTHENTICATED

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The request has no valid session.")


class ForbiddenRoleError(BackendError):
    """The role of the account may not call the operation (contract `ForbiddenRole`)."""

    code: ClassVar[ErrorCode] = ErrorCode.FORBIDDEN

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The role of this account may not call this operation.")


class ForbiddenOriginError(BackendError):
    """The `Origin` header is missing or not allowed (ADR-0009, statement 7)."""

    code: ClassVar[ErrorCode] = ErrorCode.FORBIDDEN

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The Origin header is missing or not allowed.")
