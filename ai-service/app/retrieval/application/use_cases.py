"""The use case of `getKbDocumentVersion`: one version of the loaded KB (UI-20)."""

from app.platform import ResourceNotFoundError
from app.release import ReleaseSource, require_release
from app.retrieval.domain import KbDocument, KbDocumentSource


class GetKbDocumentVersion:
    """Return the full text and metadata of one document version of the loaded KB."""

    def __init__(self, release_source: ReleaseSource, documents: KbDocumentSource) -> None:
        """Keep the source of the loaded release and of its KB documents.

        Args:
            release_source: Where the loaded release comes from.
            documents: Where the document versions of a release come from.
        """
        self._release_source = release_source
        self._documents = documents

    def execute(self, document_id: str, version: str) -> KbDocument:
        """Find the document version in the loaded KB.

        Args:
            document_id: The document.
            version: The version of the document.

        Returns:
            The document version.

        Raises:
            ReleaseNotLoadedError: No verified release is loaded.
            ResourceNotFoundError: The loaded KB has no such version, also when only an
                earlier KB contained it.
        """
        release = require_release(self._release_source)
        document = self._documents.find(document_id, version, release)
        if document is None:
            raise ResourceNotFoundError
        return document
