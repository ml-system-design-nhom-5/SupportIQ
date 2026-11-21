"""Public API of retrieval: the KB document versions of the loaded KB and their search (ARCH-17)."""

from app.retrieval.application import GetKbDocumentVersion
from app.retrieval.domain import (
    DocumentMatch,
    DocumentSearch,
    KbDocument,
    KbDocumentSource,
    RetrievalError,
)

__all__ = [
    "DocumentMatch",
    "DocumentSearch",
    "GetKbDocumentVersion",
    "KbDocument",
    "KbDocumentSource",
    "RetrievalError",
]
