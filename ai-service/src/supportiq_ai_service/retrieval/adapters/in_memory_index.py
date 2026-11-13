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
    allowed_doc_version_keys: Optional[set] = None,  # P1: Filter eligible (doc_id, version) keys BEFORE ranking
) -> RetrievalResult:
    """Exact cosine similarity search over eligible policy chunks.
    Filters eligible chunks BEFORE ranking, groups results to return up to top_k_docs distinct documents,
    and strictly respects token_budget.
    """
    if index.is_empty():
        return RetrievalResult(status="no_evidence", reason_codes=["empty_index"])

    # P1: Determine eligible indices prior to ranking
    eligible_indices = []
    for i, c in enumerate(index.chunks):
        if allowed_doc_version_keys is not None:
            doc_ver_key = (c["doc_id"], c.get("version", "1.0"))
            if doc_ver_key not in allowed_doc_version_keys:
                continue
        eligible_indices.append(i)

    if not eligible_indices:
        return RetrievalResult(status="no_evidence", reason_codes=["no_eligible_chunks"])

    try:
        # Encode query with prefix (shape: (1, 384))
        q_emb = encoder.encode_queries([query])[0]
    except Exception as e:
        return RetrievalResult(status="error", reason_codes=["encoder_failed", str(e)])

    # Dot product of normalized vectors equals exact cosine similarity
    sub_embeddings = index.embeddings[eligible_indices]
    scores = np.dot(sub_embeddings, q_emb)

    if len(scores) == 0:
        return RetrievalResult(status="no_evidence", reason_codes=["no_chunks"])

    max_score = float(np.max(scores))
    if max_score < threshold:
        return RetrievalResult(
            status="no_evidence",
            top_score=max_score,
            reason_codes=["below_relevance_threshold"]
        )

    # Sort eligible chunk indices descending by similarity
    sorted_sub_indices = np.argsort(scores)[::-1]

    # P2: Group chunks by doc_id while respecting token_budget
    docs_map: Dict[str, Dict[str, Any]] = {}
    total_tokens_used = 0

    for sub_idx in sorted_sub_indices:
        score = float(scores[sub_idx])
        if score < threshold:
            continue

        orig_idx = eligible_indices[sub_idx]
        chunk = index.chunks[orig_idx]
        doc_id = chunk["doc_id"]
        chunk_token_count = chunk.get("token_count", len(chunk["text"].split()))

        # Check if adding this chunk exceeds token_budget
        if total_tokens_used + chunk_token_count > token_budget:
            # Token budget reached, skip further chunks
            continue

        if doc_id not in docs_map:
            if len(docs_map) >= top_k_docs:
                continue
            docs_map[doc_id] = {
                "doc_id": doc_id,
                "version": chunk.get("version"),
                "category": chunk.get("category"),
                "title": chunk.get("title"),
                "score": score,
                "content_hash": chunk.get("content_hash"),
                "chunks": [chunk],
            }
            total_tokens_used += chunk_token_count
        else:
            if len(docs_map[doc_id]["chunks"]) < max_chunks_per_doc:
                docs_map[doc_id]["chunks"].append(chunk)
                total_tokens_used += chunk_token_count

    selected_docs = list(docs_map.values())
    if not selected_docs:
        return RetrievalResult(status="no_evidence", reason_codes=["token_budget_exceeded"])

    return RetrievalResult(
        status="success",
        documents=selected_docs,
        top_score=max_score,
        reason_codes=[],
    )
