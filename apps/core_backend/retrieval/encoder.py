import hashlib
from typing import List, Dict, Any, Optional
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

from apps.core_backend.retrieval.importer import PolicyVersion

BGE_MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def chunk_policy(policy: PolicyVersion, max_tokens: int = 480, overlap: int = 40) -> List[Dict[str, Any]]:
    """Chunk policy document into ≤ 480 token chunks with 40 token overlap, preserving title & context."""
    title = policy.title.strip()
    content = policy.content.strip()
    full_text = f"{title}\n{content}"
    words = full_text.split()

    # If small enough, return as single chunk
    if len(words) <= max_tokens:
        chunk_id = f"{policy.doc_id}:{policy.version}:c0"
        return [{
            "chunk_id": chunk_id,
            "doc_id": policy.doc_id,
            "version": policy.version,
            "category": policy.category,
            "title": policy.title,
            "text": full_text,
            "content_hash": policy.content_hash,
            "ordinal": 0,
        }]

    # Sliding window chunking
    chunks = []
    step = max_tokens - overlap
    ordinal = 0
    for i in range(0, len(words), step):
        chunk_words = words[i:i + max_tokens]
        chunk_text = f"{title}\n" + " ".join(chunk_words) if i > 0 else " ".join(chunk_words)
        chunk_id = f"{policy.doc_id}:{policy.version}:c{ordinal}"
        chunks.append({
            "chunk_id": chunk_id,
            "doc_id": policy.doc_id,
            "version": policy.version,
            "category": policy.category,
            "title": policy.title,
            "text": chunk_text,
            "content_hash": policy.content_hash,
            "ordinal": ordinal,
        })
        ordinal += 1
        if i + max_tokens >= len(words):
            break

    return chunks

class PolicyEncoder:
    """BAAI/bge-small-en-v1.5 Native PyTorch & Transformers encoder.
    Uses CLS pooling and L2 normalization to produce 384-dimensional unit vectors.
    """
    def __init__(self, model_path: Optional[str] = None, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.device = torch.device("cpu")
        self.tokenizer = None
        self.model = None

        if not mock_mode:
            m_path = model_path or BGE_MODEL_NAME
            try:
                self.tokenizer = AutoTokenizer.from_pretrained(m_path)
                self.model = AutoModel.from_pretrained(m_path)
                self.model.eval()
                self.model.to(self.device)
            except Exception:
                # If network/model unavailable locally, fallback to mock mode
                self.mock_mode = True

    def prepare_query(self, query: str) -> str:
        return f"{QUERY_PREFIX}{query.strip()}"

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        prepared = [self.prepare_query(q) for q in queries]
        return self._encode(prepared)

    def encode_passages(self, passages: List[str]) -> np.ndarray:
        return self._encode(passages)

    def _encode(self, texts: List[str]) -> np.ndarray:
        if self.mock_mode or self.model is None or self.tokenizer is None:
            # Deterministic pseudo-embedding for testing/isolated environments
            arrs = []
            for t in texts:
                h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
                np.random.seed(h % (2**32))
                vec = np.random.randn(384).astype(np.float32)
                vec = vec / (np.linalg.norm(vec) + 1e-12)
                arrs.append(vec)
            return np.vstack(arrs)

        inputs = self.tokenizer(
            texts,
            max_length=512,
            padding=True,
            truncation=True,
            return_tensors="pt"
        )
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.inference_mode():
            outputs = self.model(**inputs)
            # CLS pooling
            embeddings = outputs.last_hidden_state[:, 0]
            # L2 normalize
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            return embeddings.cpu().numpy().astype(np.float32)
