"""Public API of pseudonymization: the only reader and writer of the pseudonym map (SEC-37).

Other features use exactly two functions: `PseudonymizeMessage.pseudonymize`, which returns the
pseudonymized text of a ticket's message, and `RestorePseudonyms.restore`, which restores the
pseudonyms of a ticket in some texts (ADR-0010, Storage and lifecycle, item 6). They also use
the placeholder syntax, to refuse a body with a placeholder (SEC-38), and the error that fails
a suggestion closed. An import-linter contract keeps every other module out of the internals.
"""

from app.pseudonymization.application import (
    MessageToPseudonymize,
    PseudonymizationPorts,
    PseudonymizationStores,
    PseudonymizeMessage,
    RestorePseudonyms,
)
from app.pseudonymization.domain import (
    PSEUDONYMIZED_TEXT_MAX_LENGTH,
    Detector,
    DetectorError,
    KnownValue,
    KnownValueDetector,
    LiteralPlaceholderDetector,
    MapTicketId,
    PatternDetector,
    PseudonymizationError,
    contains_placeholder,
)

__all__ = [
    "PSEUDONYMIZED_TEXT_MAX_LENGTH",
    "Detector",
    "DetectorError",
    "KnownValue",
    "KnownValueDetector",
    "LiteralPlaceholderDetector",
    "MapTicketId",
    "MessageToPseudonymize",
    "PatternDetector",
    "PseudonymizationError",
    "PseudonymizationPorts",
    "PseudonymizationStores",
    "PseudonymizeMessage",
    "RestorePseudonyms",
    "contains_placeholder",
]
