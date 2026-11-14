"""Interface layer of retrieval."""

from supportiq_ai_service.retrieval.api.routes import build_retrieval_router, kb_document_body

__all__ = ["build_retrieval_router", "kb_document_body"]
