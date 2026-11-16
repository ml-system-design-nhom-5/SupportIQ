"""The search of the KB by the content of a message, and the port that runs it.

Retrieval uses the content of the message only, never the predicted intent (ADR-0005,
statement 1). It returns every relevant document version, whatever its validity: validity at
`as_of` and reranking come after it, before the top documents are chosen (statements 2 and 3).
"""

from dataclasses import dataclass
from typing import ClassVar, Protocol

from supportiq_ai_service.platform import AiServiceError, ErrorCode
from supportiq_ai_service.retrieval.domain.kb_document import KbDocument


@dataclass(frozen=True, slots=True)
class DocumentMatch:
    """A KB document version with passages that match a message.

    Attributes:
        document: The document version.
        score: The similarity of its best passage to the message.
        snippets: Its matching passages, best first. Each is a passage of its body.
    """

    document: KbDocument
    score: float
    snippets: tuple[str, ...]


class RetrievalError(AiServiceError):
    """The search of the KB failed: a technical failure, never a lack of evidence."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The search of the KB failed.")


class DocumentSearch(Protocol):
    """Find the KB document versions that are relevant to a message."""

    def search(self, message: str) -> tuple[DocumentMatch, ...]:
        """Search the KB of the loaded release.

        Args:
            message: The pseudonymized message. Confidential.

        Returns:
            Every relevant document version, best match first; none when nothing is relevant.

        Raises:
            RetrievalError: The search failed.
        """
        ...
