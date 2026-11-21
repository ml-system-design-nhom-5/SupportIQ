"""Admit a KB document version only when the KB holder released it and its fields are valid.

ADR-0021 (KB ingestion, statement 1) admits a version only when both hold: the release file of
the KB holder lists it, and every field that `KbDocumentVersion` requires is present with the
type, length, and pattern of the contract (DATA-12). Every other record is quarantined with
every reason (DATA-13). Ingestion never invents a value: a version written as a number is not
turned into text, and a missing field is never filled in.

The fields of the KB file map to those of `KbDocumentVersion` as ADR-0021 records them
(statement 2): `content` is the `body`, `valid_from` and `valid_to` are the effective period,
`approved_by` is the `owner` unchanged, and the `source` is the name of the KB file with its KB
version. `supported_intents` goes to the document-to-intent mapping (statement 4).

DATA-12 also asks for matching checksums: the declared `content_hash` must be the SHA-256 of
`content` in UTF-8, as the importer of `main` required.
"""

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import cast

from supportiq_release.kb_ingestion.domain.conflicts import find_conflicts
from supportiq_release.kb_ingestion.domain.records import (
    AdmittedVersion,
    DocumentVersionKey,
    IngestionResult,
    KbField,
    QuarantineCode,
    QuarantinedRecord,
    QuarantineReason,
    RawKb,
    TextDigest,
)

# The pattern of `KbDocumentId` and `KbDocumentVersionTag` in the contract.
KB_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
# The pattern of `Timestamp` in the contract: RFC 3339 in UTC with `Z` (CON-17).
_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]{1,6})?Z"
)
# A SHA-256 in lowercase hexadecimal, as `hashlib` writes it.
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True, slots=True)
class _TextField:
    # A text field of the KB file, with the limits of its field of `KbDocumentVersion`. A
    # field with a pattern has no length of its own: the pattern bounds it.
    name: KbField
    max_length: int | None = None
    pattern: re.Pattern[str] | None = None
    required: bool = True


_DOCUMENT_ID = _TextField(KbField.DOCUMENT_ID, pattern=KB_IDENTIFIER_PATTERN)
_VERSION = _TextField(KbField.VERSION, pattern=KB_IDENTIFIER_PATTERN)
_TITLE = _TextField(KbField.TITLE, 200)
_CONTENT = _TextField(KbField.CONTENT, 20_000)
_CONTENT_HASH = _TextField(KbField.CONTENT_HASH, pattern=_SHA256_PATTERN)
_POLICY_KEY = _TextField(KbField.POLICY_KEY, 100)
_VALID_FROM = _TextField(KbField.VALID_FROM, pattern=_TIMESTAMP_PATTERN)
_VALID_TO = _TextField(KbField.VALID_TO, pattern=_TIMESTAMP_PATTERN, required=False)
_APPROVED_BY = _TextField(KbField.APPROVED_BY, 100)
_TEXT_FIELDS = (
    _DOCUMENT_ID,
    _VERSION,
    _TITLE,
    _CONTENT,
    _CONTENT_HASH,
    _POLICY_KEY,
    _VALID_FROM,
    _VALID_TO,
    _APPROVED_BY,
)


@dataclass(frozen=True, slots=True)
class _Context:
    # What every record of one raw KB is checked against.
    released: frozenset[DocumentVersionKey]
    counts: Counter[DocumentVersionKey]
    intent_labels: frozenset[str]
    digest: TextDigest


def admit(kb: RawKb, intent_labels: frozenset[str], digest: TextDigest) -> IngestionResult:
    """Admit or quarantine every record of a raw KB.

    Args:
        kb: The raw KB folder.
        intent_labels: The 46 intent labels of the contract.
        digest: The SHA-256 of a text in UTF-8, in lowercase hexadecimal.

    Returns:
        The admitted versions, the quarantined records with every reason, the conflicts
        between admitted versions, and the released versions that the KB file lacks.
    """
    keys = [_key(record) for record in kb.records]
    context = _Context(
        released=kb.released,
        counts=Counter(key for key in keys if key is not None),
        intent_labels=intent_labels,
        digest=digest,
    )
    admitted: list[AdmittedVersion] = []
    quarantined: list[QuarantinedRecord] = []
    for position, (record, key) in enumerate(zip(kb.records, keys, strict=True)):
        reasons = _reasons(record, key, context)
        if reasons:
            quarantined.append(_quarantined(position, record, reasons))
        else:
            admitted.append(_admitted(record, kb))
    admitted.sort(key=lambda version: version.key)
    present = {key for key in keys if key is not None}
    return IngestionResult(
        kb_version=kb.kb_version,
        admitted=tuple(admitted),
        quarantined=tuple(quarantined),
        conflicts=find_conflicts(admitted),
        released_but_absent=tuple(sorted(kb.released - present)),
    )


def _key(record: Mapping[str, object]) -> DocumentVersionKey | None:
    # The pair that the release file lists, when both values are texts.
    document_id, version = record.get(_DOCUMENT_ID.name), record.get(_VERSION.name)
    if isinstance(document_id, str) and isinstance(version, str):
        return (document_id, version)
    return None


def _reasons(
    record: Mapping[str, object], key: DocumentVersionKey | None, context: _Context
) -> list[QuarantineReason]:
    reasons = [reason for field in _TEXT_FIELDS if (reason := _text_reason(record, field))]
    if key is None or key not in context.released:
        reasons.append(QuarantineReason(QuarantineCode.NOT_IN_RELEASE))
    if key is not None and context.counts[key] > 1:
        # Two records of one version: ingestion cannot know which one the KB holder released.
        reasons.append(QuarantineReason(QuarantineCode.DUPLICATE_VERSION))
    starts, ends = _time(record.get(KbField.VALID_FROM)), _time(record.get(KbField.VALID_TO))
    if starts is not None and ends is not None and ends <= starts:
        reasons.append(QuarantineReason(QuarantineCode.INVALID_FIELD, KbField.VALID_TO))
    if not _checksum_matches(record, context.digest):
        reasons.append(QuarantineReason(QuarantineCode.INVALID_FIELD, KbField.CONTENT_HASH))
    reasons.extend(_intent_reasons(record.get(KbField.SUPPORTED_INTENTS), context.intent_labels))
    return reasons


def _text_reason(record: Mapping[str, object], field: _TextField) -> QuarantineReason | None:
    # A JSON null counts as missing, because the contract never uses null (CON-08).
    value = record.get(field.name)
    if value is None:
        return (
            QuarantineReason(QuarantineCode.MISSING_FIELD, field.name) if field.required else None
        )
    if not isinstance(value, str) or not _fits(value, field):
        return QuarantineReason(QuarantineCode.INVALID_FIELD, field.name)
    return None


def _fits(value: str, field: _TextField) -> bool:
    if not _encodes(value):
        return False
    if field.pattern is not None:
        matches = field.pattern.fullmatch(value) is not None
        return matches and (field.pattern is not _TIMESTAMP_PATTERN or _time(value) is not None)
    # A text needs one character that is not white space, as `main` required of `approved_by`.
    return bool(value.strip()) and (field.max_length is None or len(value) <= field.max_length)


def _encodes(value: str) -> bool:
    # JSON allows a lone surrogate, such as `\ud800`, which UTF-8 cannot write.
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _checksum_matches(record: Mapping[str, object], digest: TextDigest) -> bool:
    # Compared only when both texts are valid: an invalid one already has its own reason.
    content, declared = record.get(KbField.CONTENT), record.get(KbField.CONTENT_HASH)
    if not isinstance(content, str) or not isinstance(declared, str):
        return True
    if not _encodes(content) or _SHA256_PATTERN.fullmatch(declared) is None:
        return True
    return digest(content) == declared


def _time(value: object) -> datetime | None:
    # The time of a valid timestamp of the contract, or None for any other value.
    if not isinstance(value, str) or _TIMESTAMP_PATTERN.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _intent_reasons(value: object, intent_labels: frozenset[str]) -> list[QuarantineReason]:
    if value is None:
        return [QuarantineReason(QuarantineCode.MISSING_FIELD, KbField.SUPPORTED_INTENTS)]
    # A list of texts, at least one, each once, as the mapping of ai-service requires. The
    # cast only names the type that `isinstance` found; each item is checked below (PY-12).
    intents = cast("list[object]", value) if isinstance(value, list) else []
    texts = [intent for intent in intents if isinstance(intent, str)]
    reasons: list[QuarantineReason] = []
    if not intents or len(texts) != len(intents) or len(set(texts)) != len(texts):
        reasons.append(QuarantineReason(QuarantineCode.INVALID_FIELD, KbField.SUPPORTED_INTENTS))
    if any(text not in intent_labels for text in texts):
        reasons.append(QuarantineReason(QuarantineCode.UNKNOWN_INTENT, KbField.SUPPORTED_INTENTS))
    return reasons


def _quarantined(
    position: int, record: Mapping[str, object], reasons: list[QuarantineReason]
) -> QuarantinedRecord:
    # Only identifiers leave the KB file: a value that is not one could hold KB text.
    return QuarantinedRecord(
        position=position,
        document_id=_identifier(record.get(_DOCUMENT_ID.name)),
        version=_identifier(record.get(_VERSION.name)),
        reasons=tuple(sorted(set(reasons), key=lambda reason: (reason.code, reason.field or ""))),
    )


def _identifier(value: object) -> str | None:
    if isinstance(value, str) and KB_IDENTIFIER_PATTERN.fullmatch(value) is not None:
        return value
    return None


def _admitted(record: Mapping[str, object], kb: RawKb) -> AdmittedVersion:
    # `_reasons` found no reason, so each field holds a valid value of its type, and each
    # cast below only names that type (PY-12, boundary parsing).
    def text(field: _TextField) -> str:
        return cast("str", record[field.name])

    effective_end_at = cast("str | None", record.get(_VALID_TO.name))
    effective_start_at = text(_VALID_FROM)
    return AdmittedVersion(
        document_id=text(_DOCUMENT_ID),
        version=text(_VERSION),
        title=text(_TITLE),
        body=text(_CONTENT),
        policy_key=text(_POLICY_KEY),
        effective_start_at=effective_start_at,
        effective_end_at=effective_end_at,
        owner=text(_APPROVED_BY),
        source=f"{kb.kb_file_name}, KB {kb.kb_version}",
        intents=tuple(cast("list[str]", record[KbField.SUPPORTED_INTENTS])),
        starts=datetime.fromisoformat(effective_start_at),
        ends=None if effective_end_at is None else datetime.fromisoformat(effective_end_at),
    )
