"""The progress of a suggestion that the console follows as a stream (ADR-0022)."""

from dataclasses import dataclass
from enum import StrEnum

from supportiq_backend.suggestions.domain.suggestions import PartStatus, SuggestionId


@dataclass(frozen=True, slots=True)
class SuggestionProgress:
    """The part statuses of a suggestion: the only values that a stream sends (SEC-01).

    Attributes:
        suggestion_id: The suggestion.
        analysis_status: The status of its analysis part.
        draft_status: The status of its draft part.
    """

    suggestion_id: SuggestionId
    analysis_status: PartStatus
    draft_status: PartStatus

    @property
    def is_pending(self) -> bool:
        """Whether a part is still `pending`."""
        return PartStatus.PENDING in (self.analysis_status, self.draft_status)

    @property
    def is_superseded(self) -> bool:
        """Whether a newer suggestion cancelled a part, so it is no longer the current one."""
        return PartStatus.CANCELLED in (self.analysis_status, self.draft_status)


class StreamEndReason(StrEnum):
    """Why a stream ended on its own (ADR-0022, statement 5)."""

    NO_PENDING_PART = "no_pending_part"
    TICKET_NOT_OPEN = "ticket_not_open"
    TIME_LIMIT = "time_limit"


@dataclass(frozen=True, slots=True)
class StreamSettings:
    """The settings of the stream (backend ticket workflow design, Settings).

    Attributes:
        poll_ms: How often a stream re-reads the part statuses.
        max_ms: The longest life of one stream.
    """

    poll_ms: int
    max_ms: int
