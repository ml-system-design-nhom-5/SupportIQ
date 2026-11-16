"""Domain types of retrieval: KB document versions, and the search of the KB."""

from supportiq_ai_service.retrieval.domain.kb_document import KbDocument, KbDocumentSource
from supportiq_ai_service.retrieval.domain.search import (
    DocumentMatch,
    DocumentSearch,
    RetrievalError,
)

__all__ = ["DocumentMatch", "DocumentSearch", "KbDocument", "KbDocumentSource", "RetrievalError"]
