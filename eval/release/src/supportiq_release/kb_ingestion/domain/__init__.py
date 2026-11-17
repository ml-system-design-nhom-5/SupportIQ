"""The rules of KB ingestion, with no file access (ARCH-11)."""

from supportiq_release.kb_ingestion.domain.admission import KB_IDENTIFIER_PATTERN, admit
from supportiq_release.kb_ingestion.domain.conflicts import find_conflicts
from supportiq_release.kb_ingestion.domain.records import (
    AdmittedVersion,
    Conflict,
    DocumentVersionKey,
    IngestionResult,
    KbField,
    QuarantineCode,
    QuarantinedRecord,
    QuarantineReason,
    RawKb,
    TextDigest,
)

__all__ = [
    "KB_IDENTIFIER_PATTERN",
    "AdmittedVersion",
    "Conflict",
    "DocumentVersionKey",
    "IngestionResult",
    "KbField",
    "QuarantineCode",
    "QuarantineReason",
    "QuarantinedRecord",
    "RawKb",
    "TextDigest",
    "admit",
    "find_conflicts",
]
