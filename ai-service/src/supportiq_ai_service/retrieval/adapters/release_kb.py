"""The KB document versions of the loaded release, for `getKbDocumentVersion` (DATA-16)."""

from collections.abc import Iterable

from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.retrieval.domain import KbDocument


class ReleaseKbDocuments:
    """Implement the `KbDocumentSource` port with the KB that a release holds."""

    def __init__(self, documents: Iterable[KbDocument]) -> None:
        """Index the document versions of the KB of a release.

        Args:
            documents: The KB document versions, which `read_kb_documents` read.
        """
        self._documents = {
            (document.document_id, document.version): document for document in documents
        }

    def find(self, document_id: str, version: str, release: LoadedRelease) -> KbDocument | None:
        """Find one document version.

        Args:
            document_id: The document.
            version: The version of the document.
            release: The loaded release, whose KB is the only one that a replica holds.

        Returns:
            The document version, or None when the KB has no such version.
        """
        del release
        return self._documents.get((document_id, version))
