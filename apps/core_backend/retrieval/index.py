from typing import List, Dict, Any, Optional
import numpy as np
from pydantic import BaseModel, Field

from apps.core_backend.retrieval.encoder import PolicyEncoder

class RetrievalResult(BaseModel):
    status: str  # "success", "no_evidence", "error"
    documents: List[Dict[str, Any]] = Field(default_factory=list)
    top_score: float = 0.0
    reason_codes: List[str] = Field(default_factory=list)

class SemanticPolicyIndex:
    """In-memory NumPy exact cosine dot-product search index for L2-normalized vectors."""
    def __init__(self, chunks: List[Dict[str, Any]], embeddings: np.ndarray, index_version: str = "v1.0.0"):
        self.chunks = chunks
        self.embeddings = embeddings  # Shape: (N, 384), float32, L2 normalized
        self.index_version = index_version

    def is_empty(self) -> bool:
        return len(self.chunks) == 0 or self.embeddings.shape[0] == 0

def search_policies(
    query: str,
    index: SemanticPolicyIndex,
    encoder: PolicyEncoder,
    threshold: float = 0.60,
    top_k_docs: int = 3,
    max_chunks_per_doc: int = 2,
    token_budget: int = 1500,
) -> RetrievalResult:
    """Exact cosine similarity search over eligible policy chunks.
    Groups results to return up to top_k_docs distinct documents.
    """
    if index.is_empty():
        return RetrievalResult(status="no_evidence", reason_codes=["empty_index"])

    try:
        # Encode query with prefix (shape: (1, 384))
        q_emb = encoder.encode_queries([query])[0]
    except Exception as e:
        return RetrievalResult(status="error", reason_codes=["encoder_failed", str(e)])

    # Dot product of normalized vectors equals exact cosine similarity
    scores = np.dot(index.embeddings, q_emb)

    if len(scores) == 0:
        return RetrievalResult(status="no_evidence", reason_codes=["no_chunks"])

    max_score = float(np.max(scores))
    if max_score < threshold:
        return RetrievalResult(
            status="no_evidence",
            top_score=round(max_score, 4),
            reason_codes=["below_relevance_threshold"]
        )

    # Sort chunk indices descending by similarity
    sorted_chunk_indices = np.argsort(scores)[::-1]

    # Group chunks by doc_id to return distinct documents
    docs_map: Dict[str, Dict[str, Any]] = {}
    for idx in sorted_chunk_indices:
        score = float(scores[idx])
        if score < threshold:
            continue

        chunk = index.chunks[idx]
        doc_id = chunk["doc_id"]

        if doc_id not in docs_map:
            if len(docs_map) >= top_k_docs:
                continue
            docs_map[doc_id] = {
                "doc_id": doc_id,
                "version": chunk.get("version"),
                "category": chunk.get("category"),
                "title": chunk.get("title"),
                "score": round(score, 4),
                "content_hash": chunk.get("content_hash"),
                "chunks": [chunk],
            }
        else:
            if len(docs_map[doc_id]["chunks"]) < max_chunks_per_doc:
                docs_map[doc_id]["chunks"].append(chunk)

    selected_docs = list(docs_map.values())
    return RetrievalResult(
        status="success",
        documents=selected_docs,
        top_score=round(max_score, 4),
        reason_codes=[],
    )
