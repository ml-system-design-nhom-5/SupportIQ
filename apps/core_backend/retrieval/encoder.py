from typing import List, Dict, Any, Optional
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

from apps.core_backend.retrieval.importer import PolicyVersion

BGE_MODEL_NAME = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def chunk_policy(
    policy: PolicyVersion,
    tokenizer: Optional[Any] = None,
    max_tokens: int = 480,
    overlap: int = 40
) -> List[Dict[str, Any]]:
    """Chunk policy document strictly using BGE tokenizer token IDs so exceptions at the end
    are NEVER silently truncated.
    """
    title = policy.title.strip()
    content = policy.content.strip()

    # Use tokenizer to get exact token IDs if available
    if tokenizer:
        title_ids = tokenizer.encode(title, add_special_tokens=False)
        content_ids = tokenizer.encode(content, add_special_tokens=False)
        # Budget for content per chunk accounts for title tokens + newline
        available_content_tokens = max(50, max_tokens - len(title_ids) - 2)

        if len(content_ids) <= available_content_tokens:
            full_text = f"{title}\n{content}"
            chunk_tokens = len(tokenizer.encode(full_text, add_special_tokens=True))
            return [{
                "chunk_id": f"{policy.doc_id}:{policy.version}:c0",
                "doc_id": policy.doc_id,
                "version": policy.version,
                "category": policy.category,
                "title": policy.title,
                "text": full_text,
                "content_hash": policy.content_hash,
                "ordinal": 0,
                "token_count": chunk_tokens,
            }]

        chunks = []
        step = max(1, available_content_tokens - overlap)
        ordinal = 0
        for i in range(0, len(content_ids), step):
            sub_content_ids = content_ids[i:i + available_content_tokens]
            sub_content_text = tokenizer.decode(sub_content_ids, skip_special_tokens=True)
            chunk_text = f"{title}\n{sub_content_text}"
            chunk_tokens = len(tokenizer.encode(chunk_text, add_special_tokens=True))
            chunks.append({
                "chunk_id": f"{policy.doc_id}:{policy.version}:c{ordinal}",
                "doc_id": policy.doc_id,
                "version": policy.version,
                "category": policy.category,
                "title": policy.title,
                "text": chunk_text,
                "content_hash": policy.content_hash,
                "ordinal": ordinal,
                "token_count": chunk_tokens,
            })
            ordinal += 1
            if i + available_content_tokens >= len(content_ids):
                break
        return chunks

    # Fallback word-based chunking with safety margin
    words = content.split()
    step = max(1, int(max_tokens * 0.7) - overlap)
    chunks = []
    ordinal = 0
    for i in range(0, len(words), step):
        sub_words = words[i:i + int(max_tokens * 0.7)]
        chunk_text = f"{title}\n" + " ".join(sub_words)
        chunks.append({
            "chunk_id": f"{policy.doc_id}:{policy.version}:c{ordinal}",
            "doc_id": policy.doc_id,
            "version": policy.version,
            "category": policy.category,
            "title": policy.title,
            "text": chunk_text,
            "content_hash": policy.content_hash,
            "ordinal": ordinal,
            "token_count": int(len(chunk_text.split()) * 1.3),
        })
        ordinal += 1
        if i + int(max_tokens * 0.7) >= len(words):
            break
    return chunks

class PolicyEncoder:
    """BAAI/bge-small-en-v1.5 Native PyTorch & Transformers encoder.
    P1 FIX: In production (mock_mode=False), failure to load model or encode raises an exception
    so system falls back to manual review, NEVER returning silent fake random vectors!
    """
    def __init__(self, model_path: Optional[str] = None, mock_mode: bool = False):
        self.mock_mode = mock_mode
        self.device = torch.device("cpu")
        self.tokenizer = None
        self.model = None

        if mock_mode:
            return

        m_path = model_path or BGE_MODEL_NAME
        try:
            self.tokenizer = AutoTokenizer.from_pretrained(m_path)
            self.model = AutoModel.from_pretrained(m_path)
            self.model.eval()
            self.model.to(self.device)
        except Exception as exc:
            # P1 FIX: Raise exception immediately in production mode!
            raise RuntimeError(f"Failed to load BGE embedding model '{m_path}': {exc}") from exc

    def prepare_query(self, query: str) -> str:
        return f"{QUERY_PREFIX}{query.strip()}"

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        prepared = [self.prepare_query(q) for q in queries]
        return self._encode(prepared)

    def encode_passages(self, passages: List[str]) -> np.ndarray:
        return self._encode(passages)

    def _encode(self, texts: List[str]) -> np.ndarray:
        if self.mock_mode:
            import hashlib
            arrs = []
            for t in texts:
                h = int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16)
                np.random.seed(h % (2**32))
                vec = np.random.randn(384).astype(np.float32)
                vec = vec / (np.linalg.norm(vec) + 1e-12)
                arrs.append(vec)
            return np.vstack(arrs)

        if self.model is None or self.tokenizer is None:
            raise RuntimeError("Model or tokenizer is not loaded")

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
