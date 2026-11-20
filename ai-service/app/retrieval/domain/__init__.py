"""Domain types of retrieval: KB document versions, and the search of the KB."""

from app.retrieval.domain.kb_document import KbDocument, KbDocumentSource
from app.retrieval.domain.search import (
    DocumentMatch,
    DocumentSearch,
    RetrievalError,
)

__all__ = ["DocumentMatch", "DocumentSearch", "KbDocument", "KbDocumentSource", "RetrievalError"]
