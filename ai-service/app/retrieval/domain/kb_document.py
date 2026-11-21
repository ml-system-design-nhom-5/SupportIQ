"""One KB document version of the loaded KB, and the port that finds it (DATA-16)."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.release import LoadedRelease


@dataclass(frozen=True, slots=True)
class KbDocument:
    """One immutable version of a KB document, with the metadata that DATA-16 requires.

    Attributes:
        document_id: The document.
        version: The version of the document.
        title: The title.
        body: The full text.
        policy_key: The policy key.
        effective_start_at: When the version takes effect, in UTC.
        effective_end_at: When it stops being in effect; None when open-ended.
        owner: Who owns the document.
        source: Where the document comes from.
        last_reviewed_at: When it was last reviewed; None when the source does not say.
    """

    document_id: str
    version: str
    title: str
    body: str
    policy_key: str
    effective_start_at: datetime
    effective_end_at: datetime | None
    owner: str
    source: str
    last_reviewed_at: datetime | None


class KbDocumentSource(Protocol):
    """Find a document version in the KB of a loaded release."""

    def find(self, document_id: str, version: str, release: LoadedRelease) -> KbDocument | None:
        """Find one document version.

        Args:
            document_id: The document.
            version: The version of the document.
            release: The loaded release, whose KB is the only one served.

        Returns:
            The document version, or None when the loaded KB has no such version.
        """
        ...
