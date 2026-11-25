"""Errors of pseudonymization: every one of them fails closed (SEC-36, ADR-0010).

No error holds a value of the message, the map, or the ticket's records (PY-23, LOG-29).
"""

from enum import StrEnum
from typing import ClassVar

from app.platform import BackendError
from app.pseudonymization.domain.placeholders import PseudonymType


class PseudonymizationFailureReason(StrEnum):
    """Why pseudonymization failed, as the audit log records it (contracts v1, Audit log)."""

    DETECTOR_ERROR = "detector_error"
    TEXT_TOO_LONG = "text_too_long"
    PSEUDONYM_LIMIT_EXCEEDED = "pseudonym_limit_exceeded"
    STORED_MAP_DIFFERS = "stored_map_differs"
    PERSONAL_DATA_LEFT = "personal_data_left"


class PseudonymizationError(BackendError):
    """Pseudonymization could not produce a text that may leave backend.

    It is deterministic: running it again on the same message fails the same way, so a
    suggestion that ends with `pseudonymization_failed` is never retried.
    """

    reason: ClassVar[PseudonymizationFailureReason] = PseudonymizationFailureReason.DETECTOR_ERROR

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The message could not be pseudonymized, so nothing was sent.")


class NamedEntityModelMissingError(BackendError):
    """The pinned named-entity model is not installed, so `backend` does not start (ERR-17)."""

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The named-entity model en_core_web_sm is not installed.")


class DetectorError(PseudonymizationError):
    """A detector could not run. A detector adapter raises it for every failure (ARCH-28)."""

    reason: ClassVar[PseudonymizationFailureReason] = PseudonymizationFailureReason.DETECTOR_ERROR


class PseudonymizedTextTooLongError(PseudonymizationError):
    """The pseudonymized text is longer than the 4 000 characters of `PseudonymizedText`."""

    reason: ClassVar[PseudonymizationFailureReason] = PseudonymizationFailureReason.TEXT_TOO_LONG


class PseudonymLimitExceededError(PseudonymizationError):
    """One type would need a pseudonym numbered above 999 (ADR-0010, item 3)."""

    reason: ClassVar[PseudonymizationFailureReason] = (
        PseudonymizationFailureReason.PSEUDONYM_LIMIT_EXCEEDED
    )


class StoredMapDiffersError(PseudonymizationError):
    """The stored map of the ticket differs from the one computed now: a defect.

    The stored map is never changed (ADR-0010, Storage and lifecycle, item 3), so a text that
    it cannot restore is never sent.
    """

    reason: ClassVar[PseudonymizationFailureReason] = (
        PseudonymizationFailureReason.STORED_MAP_DIFFERS
    )


class PersonalDataLeftError(PseudonymizationError):
    """The pre-send check found personal data in the built text: a detector missed a part.

    It is a defect of a detector (ADR-0029, statements 4 and 5). For the event, it keeps the
    type of what the check found: the type of the value, or of the placeholder beside a residue.
    It never keeps the value.
    """

    reason: ClassVar[PseudonymizationFailureReason] = (
        PseudonymizationFailureReason.PERSONAL_DATA_LEFT
    )

    def __init__(self, pseudonym_type: PseudonymType) -> None:
        """Build the error with its fixed detail.

        Args:
            pseudonym_type: The type of what the check found.
        """
        super().__init__()
        self.pseudonym_type = pseudonym_type
