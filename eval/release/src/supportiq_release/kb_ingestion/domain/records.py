"""The records of KB ingestion: what the raw KB holds, and what ingestion makes of it."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

type DocumentVersionKey = tuple[str, str]
# The SHA-256 of a text in UTF-8, in lowercase hexadecimal. The domain gets it as a function,
# because it computes no checksum itself (ARCH-11).
type TextDigest = Callable[[str], str]


class KbField(StrEnum):
    """The fields of the KB file that ingestion reads."""

    DOCUMENT_ID = "document_id"
    VERSION = "version"
    TITLE = "title"
    CONTENT = "content"
    CONTENT_HASH = "content_hash"
    POLICY_KEY = "policy_key"
    VALID_FROM = "valid_from"
    VALID_TO = "valid_to"
    APPROVED_BY = "approved_by"
    SUPPORTED_INTENTS = "supported_intents"


@dataclass(frozen=True, slots=True)
class RawKb:
    """One raw KB folder, read but not checked: `data/raw/kb/<kb_version>/` (DATA-06).

    The reader of the folder guarantees that `kb_version` matches the pattern of a KB
    identifier and that `kb_file_name` holds at most 100 characters, so the `source` of each
    admitted version fits the 200 characters of the contract.

    Attributes:
        kb_version: The KB version, the name of the folder.
        kb_file_name: The name of the KB file, which the field `source` of every admitted
            version names (ADR-0021, KB ingestion, statement 2).
        released: The document versions that the release file of the KB holder lists.
        records: The objects of the KB file, in their order.
    """

    kb_version: str
    kb_file_name: str
    released: frozenset[DocumentVersionKey]
    records: tuple[Mapping[str, object], ...]


class QuarantineCode(StrEnum):
    """Why ingestion did not admit a record (DATA-13)."""

    NOT_IN_RELEASE = "not_in_release"
    MISSING_FIELD = "missing_field"
    INVALID_FIELD = "invalid_field"
    DUPLICATE_VERSION = "duplicate_version"
    UNKNOWN_INTENT = "unknown_intent"


@dataclass(frozen=True, slots=True)
class QuarantineReason:
    """One reason to quarantine a record.

    Attributes:
        code: The reason.
        field: The field of the KB file that the reason is about, if any.
    """

    code: QuarantineCode
    field: KbField | None = None


@dataclass(frozen=True, slots=True)
class QuarantinedRecord:
    """A record that ingestion did not admit, with every reason, and no text of the KB.

    Attributes:
        position: The place of the record in the KB file, from 0.
        document_id: The document ID, only when it is a valid identifier.
        version: The version, only when it is a valid identifier.
        reasons: Every reason, sorted by code, then by field.
    """

    position: int
    document_id: str | None
    version: str | None
    reasons: tuple[QuarantineReason, ...]


@dataclass(frozen=True, slots=True)
class AdmittedVersion:
    """A KB document version with every field of `KbDocumentVersion`, and its intents.

    The texts are those of the KB file, unchanged. `effective_start_at` and `effective_end_at`
    keep the text of the file, and `starts` and `ends` hold the same times, for the checks.

    Attributes:
        document_id: The document ID.
        version: The version.
        title: The title.
        body: The full text.
        policy_key: The policy key.
        effective_start_at: When the version takes effect.
        effective_end_at: When it stops being in effect, or None when it is open-ended.
        owner: The owner, the value of `approved_by` (ADR-0021, KB ingestion, statement 2).
        source: The name of the KB file with its KB version.
        intents: The intents of `supported_intents`, in their order (statement 4).
        starts: The time of `effective_start_at`.
        ends: The time of `effective_end_at`, or None.
    """

    document_id: str
    version: str
    title: str
    body: str
    policy_key: str
    effective_start_at: str
    effective_end_at: str | None
    owner: str
    source: str
    intents: tuple[str, ...]
    starts: datetime
    ends: datetime | None

    @property
    def key(self) -> DocumentVersionKey:
        """Return the document ID and the version."""
        return (self.document_id, self.version)


@dataclass(frozen=True, slots=True)
class Conflict:
    """Two admitted versions that `ai-service` shows as `conflicting` at some `as_of`.

    Attributes:
        first: The first version, in the order of the keys.
        second: The second version.
    """

    first: DocumentVersionKey
    second: DocumentVersionKey


@dataclass(frozen=True, slots=True)
class IngestionResult:
    """What ingestion made of one raw KB folder.

    Attributes:
        kb_version: The KB version.
        admitted: The admitted versions, in the order of their keys.
        quarantined: The quarantined records, in their order in the KB file.
        conflicts: The conflicts between admitted versions, which stay admitted (DATA-19).
        released_but_absent: The versions that the release file lists and the KB file lacks.
    """

    kb_version: str
    admitted: tuple[AdmittedVersion, ...]
    quarantined: tuple[QuarantinedRecord, ...]
    conflicts: tuple[Conflict, ...]
    released_but_absent: tuple[DocumentVersionKey, ...]

    @property
    def needs_accepted_quarantine(self) -> bool:
        """Whether the run fails until an issue accepts what it did not admit (DATA-13).

        Both a quarantined record and a released version that the KB file lacks make the
        served KB differ from the release of the KB holder, so both wait for the issue.
        """
        return bool(self.quarantined or self.released_but_absent)
