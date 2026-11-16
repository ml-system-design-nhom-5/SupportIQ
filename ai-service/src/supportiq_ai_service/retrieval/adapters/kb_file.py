"""The interim format of the KB of a release: the KB document versions that ingestion admitted.

KB ingestion in `eval/` writes the file and admits a version only when every field that
`KbDocumentVersion` requires is present (ADR-0021, KB ingestion). Each document holds the
fields of `KbDocumentVersion` in the `ai-service` contract, with its patterns and lengths, so
`getKbDocumentVersion` serves them as they are. The first release holds no document. A data
contract in `contracts/` replaces this format (ADR-0021, Follow-ups).
"""

from typing import Annotated, Literal, Self

from pydantic import StringConstraints, model_validator

from supportiq_ai_service.release.assets import (
    AssetFiles,
    AssetVersionText,
    StrictDocument,
    UtcTimestamp,
    read_json_asset,
)
from supportiq_ai_service.retrieval.domain import KbDocument

KB_FORMAT = "supportiq-kb/interim-1"
# The pattern of `KbDocumentId` and of `KbDocumentVersionTag` in the contract.
_KB_IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"

KbIdentifier = Annotated[str, StringConstraints(pattern=_KB_IDENTIFIER_PATTERN)]


def _text(max_length: int) -> StringConstraints:
    return StringConstraints(min_length=1, max_length=max_length)


class _KbDocumentEntry(StrictDocument):
    document_id: KbIdentifier
    version: KbIdentifier
    title: Annotated[str, _text(200)]
    body: Annotated[str, _text(20_000)]
    policy_key: Annotated[str, _text(100)]
    effective_start_at: UtcTimestamp
    effective_end_at: UtcTimestamp | None = None
    owner: Annotated[str, _text(100)]
    source: Annotated[str, _text(200)]
    last_reviewed_at: UtcTimestamp | None = None

    @model_validator(mode="after")
    def _ends_after_it_starts(self) -> Self:
        if self.effective_end_at is not None and self.effective_end_at <= self.effective_start_at:
            message = "a version stops being in effect after it takes effect"
            raise ValueError(message)
        return self


class _KbFile(StrictDocument):
    format: Literal["supportiq-kb/interim-1"]
    kb_version: AssetVersionText
    documents: tuple[_KbDocumentEntry, ...]

    @model_validator(mode="after")
    def _each_version_once(self) -> Self:
        keys = [(entry.document_id, entry.version) for entry in self.documents]
        if len(set(keys)) != len(keys):
            message = "each document version appears once"
            raise ValueError(message)
        return self


def read_kb_documents(files: AssetFiles) -> tuple[KbDocument, ...]:
    """Read the KB of a verified release.

    Args:
        files: The files of the KB asset, which holds one file.

    Returns:
        Every KB document version of the release, possibly none.

    Raises:
        ReleaseInvalidError: The asset holds more than one file, or the file breaks the
            format or names another KB version.
    """
    kb_file = files.sole()
    content = read_json_asset(kb_file, _KbFile)
    if content.kb_version != files.version:
        raise kb_file.invalid()
    return tuple(
        KbDocument(
            document_id=entry.document_id,
            version=entry.version,
            title=entry.title,
            body=entry.body,
            policy_key=entry.policy_key,
            effective_start_at=entry.effective_start_at,
            effective_end_at=entry.effective_end_at,
            owner=entry.owner,
            source=entry.source,
            last_reviewed_at=entry.last_reviewed_at,
        )
        for entry in content.documents
    )
