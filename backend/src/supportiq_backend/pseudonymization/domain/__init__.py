"""Domain of pseudonymization: placeholders, detectors, and the pseudonym map (ADR-0010)."""

from supportiq_backend.pseudonymization.domain.detection import (
    Detection,
    DetectionSource,
    Detector,
    KnownValue,
    drop_product_names,
    resolve_overlaps,
)
from supportiq_backend.pseudonymization.domain.detectors import (
    KnownValueDetector,
    LiteralPlaceholderDetector,
    PatternDetector,
    is_luhn_valid,
)
from supportiq_backend.pseudonymization.domain.errors import (
    DetectorError,
    NamedEntityModelMissingError,
    PseudonymizationError,
    PseudonymizationFailureReason,
    PseudonymizedTextTooLongError,
    PseudonymLimitExceededError,
    StoredMapDiffersError,
)
from supportiq_backend.pseudonymization.domain.placeholders import (
    PLACEHOLDER_PATTERN,
    PseudonymType,
    contains_placeholder,
)
from supportiq_backend.pseudonymization.domain.ports import MapTicketId, PseudonymMapStore
from supportiq_backend.pseudonymization.domain.pseudonym_map import (
    PSEUDONYMIZED_TEXT_MAX_LENGTH,
    PseudonymEntry,
    PseudonymizedMessage,
    RestoredText,
    build_pseudonymized_message,
    restore_pseudonyms,
)

__all__ = [
    "PLACEHOLDER_PATTERN",
    "PSEUDONYMIZED_TEXT_MAX_LENGTH",
    "Detection",
    "DetectionSource",
    "Detector",
    "DetectorError",
    "KnownValue",
    "KnownValueDetector",
    "LiteralPlaceholderDetector",
    "MapTicketId",
    "NamedEntityModelMissingError",
    "PatternDetector",
    "PseudonymEntry",
    "PseudonymLimitExceededError",
    "PseudonymMapStore",
    "PseudonymType",
    "PseudonymizationError",
    "PseudonymizationFailureReason",
    "PseudonymizedMessage",
    "PseudonymizedTextTooLongError",
    "RestoredText",
    "StoredMapDiffersError",
    "build_pseudonymized_message",
    "contains_placeholder",
    "drop_product_names",
    "is_luhn_valid",
    "resolve_overlaps",
    "restore_pseudonyms",
]
