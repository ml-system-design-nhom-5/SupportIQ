"""Errors of suggestions and of the ticket checks that suggestions share with tickets.

Each detail is the one of its contract example in `contracts/examples/problems/` (CON-06).
"""

from typing import ClassVar

from supportiq_backend.platform import (
    BackendError,
    ErrorCode,
    InvalidRequestError,
    ResourceNotFoundError,
)

# The state that refuses a suggestion on a ticket in manual mode (contract `SuggestionConflict`).
MANUAL_MODE_STATE = "in manual mode"


class InvalidTicketStateError(BackendError):
    """The operation is not allowed in the ticket's state or handling mode (409)."""

    code: ClassVar[ErrorCode] = ErrorCode.INVALID_TICKET_STATE

    def __init__(self, state: str) -> None:
        """Build the error from the state that refuses the operation.

        Args:
            state: The ticket status, such as `closed`, or `in manual mode`.
        """
        super().__init__(f"The ticket is {state}, so this operation is not allowed.")


class SuggestionPendingError(BackendError):
    """A part of the current suggestion is still `pending` (409)."""

    code: ClassVar[ErrorCode] = ErrorCode.SUGGESTION_PENDING

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__(
            "A part of the current suggestion is still pending. Try again when it is no longer"
            " pending."
        )


class SuggestionSupersededError(BackendError):
    """A `suggestion_id` of the body is not the ticket's current suggestion (409)."""

    code: ClassVar[ErrorCode] = ErrorCode.SUGGESTION_SUPERSEDED

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The suggestion_id is not the ticket's current suggestion.")


class NoIntentKnownError(InvalidRequestError):
    """An intent correction came while no intent is known and nothing is pending (422)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__(
            "No intent is known yet, so the intent cannot be corrected. Retry the AI or reply"
            " without a draft."
        )


class NothingToRetryError(InvalidRequestError):
    """A retry came while the current suggestion has no failure that a retry can fix (422)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The current suggestion has no part that a retry can fix.")


class KbDocumentVersionNotFoundError(ResourceNotFoundError):
    """The loaded KB has no such document version, or a path parameter names none (404)."""


class AiServiceUnavailableError(BackendError):
    """`ai-service` timed out, was unreachable, or answered `5xx` (ERR-08).

    A suggestion part becomes `unavailable` with `ai_service_unavailable`; a read of the
    console answers `503 not-ready`, with the detail of the example `ai-service-not-ready`.
    """

    code: ClassVar[ErrorCode] = ErrorCode.NOT_READY

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("ai-service did not answer in time.")


class AiServiceContractError(AiServiceUnavailableError):
    """`ai-service` refused the request with `4xx`, or answered outside its contract.

    Both are defects (contracts v1 design, Suggestion lifecycle), and both make a part
    `unavailable` like any failure of `ai-service`: an unknown reason code could be one that
    requires authority (CON-22).
    """
