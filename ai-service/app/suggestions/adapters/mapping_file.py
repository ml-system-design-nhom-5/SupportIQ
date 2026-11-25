"""The interim format of the document-to-intent mapping of a release (ADR-0005, statement 6).

KB ingestion copies `supported_intents` of the KB source into this file, and the KB file stays
unchanged (ADR-0021, KB ingestion, statement 4). The mapping names only document versions of
the KB of the same release. A data contract in `contracts/` replaces this format (ADR-0021,
Follow-ups).
"""

from collections.abc import Collection
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from app.release.assets import (
    AssetFiles,
    AssetVersionText,
    StrictDocument,
    read_json_asset,
)
from app.retrieval import KbDocument
from app.suggestions.adapters.intent_label_field import IntentLabelField
from app.suggestions.domain import DocumentIntents

MAPPING_FORMAT = "supportiq-document-intents/interim-1"


class _MappingEntry(StrictDocument):
    # The identifiers are checked against the KB of the release, which checks their pattern.
    document_id: str
    version: str
    intents: Annotated[tuple[IntentLabelField, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def _each_intent_once(self) -> Self:
        if len(set(self.intents)) != len(self.intents):
            message = "each intent of a document version appears once"
            raise ValueError(message)
        return self


class _MappingFile(StrictDocument):
    format: Literal["supportiq-document-intents/interim-1"]
    version: AssetVersionText
    kb_version: AssetVersionText
    documents: tuple[_MappingEntry, ...]

    @model_validator(mode="after")
    def _each_version_once(self) -> Self:
        keys = [(entry.document_id, entry.version) for entry in self.documents]
        if len(set(keys)) != len(keys):
            message = "each document version appears once"
            raise ValueError(message)
        return self


def read_document_intents(
    files: AssetFiles, kb_version: str, kb_documents: Collection[KbDocument]
) -> DocumentIntents:
    """Read the mapping asset of a verified release.

    Args:
        files: The files of the mapping asset, which holds one file.
        kb_version: The KB version of the same release.
        kb_documents: The KB document versions of the same release.

    Returns:
        The intents of each document version that the mapping names.

    Raises:
        ReleaseInvalidError: The asset holds more than one file, or the file breaks the
            format, names another mapping or KB version, or names a document version that
            the KB does not hold.
    """
    mapping_file = files.sole()
    content = read_json_asset(mapping_file, _MappingFile)
    if content.version != files.version or content.kb_version != kb_version:
        raise mapping_file.invalid()
    known_versions = {(document.document_id, document.version) for document in kb_documents}
    if any((entry.document_id, entry.version) not in known_versions for entry in content.documents):
        raise mapping_file.invalid()
    return DocumentIntents(
        intents_by_document=MappingProxyType(
            {
                (entry.document_id, entry.version): frozenset(entry.intents)
                for entry in content.documents
            }
        )
    )
