"""The KB documents while no KB is wired to the release: none."""

from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.retrieval.domain import KbDocument


class NoKbDocuments:
    """Implement the `KbDocumentSource` port while no KB is wired to a release."""

    def find(self, document_id: str, version: str, release: LoadedRelease) -> KbDocument | None:
        """Find nothing.

        Args:
            document_id: The document.
            version: The version of the document.
            release: The loaded release.

        Returns:
            None: no KB is loaded.
        """
        del document_id, version, release
        return None
