"""The document-to-intent mapping of a release, a versioned file apart from the KB.

Reranking adds λ times the probability of the intents of each document version to its
retrieval score (ADR-0005, statements 3 and 6). The KB itself is never modified.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from app.suggestions.domain.request import IntentName


@dataclass(frozen=True, slots=True)
class DocumentIntents:
    """The intents that each KB document version of a release answers.

    Attributes:
        intents_by_document: The intents of each version, by document ID and version. A
            version that the mapping does not name answers no intent.
    """

    intents_by_document: Mapping[tuple[str, str], frozenset[IntentName]]

    def intents_of(self, document_id: str, version: str) -> frozenset[IntentName]:
        """Return the intents of one document version.

        Args:
            document_id: The document.
            version: The version of the document.

        Returns:
            Its intents, possibly none.
        """
        return self.intents_by_document.get((document_id, version), frozenset())
