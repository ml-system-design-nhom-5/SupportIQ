"""Interface layer of retrieval."""

from app.retrieval.api.routes import build_retrieval_router, kb_document_body

__all__ = ["build_retrieval_router", "kb_document_body"]
