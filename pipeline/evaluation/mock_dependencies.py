"""Offline mock dependencies for zero-network benchmark runs and mock profiles."""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List, Optional
import numpy as np

from apps.core_backend.intent.schemas import IntentPrediction
from apps.core_backend.llm.gemini import LLMError
from apps.core_backend.safety import split_draft_sentences


_STOPWORDS = frozenset([
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and", "any", "are",
    "as", "at", "be", "because", "been", "before", "being", "below", "between", "both", "but",
    "by", "can", "did", "do", "does", "doing", "don", "down", "during", "each", "few", "for",
    "from", "further", "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
    "him", "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself", "just",
    "me", "more", "most", "my", "myself", "no", "nor", "not", "now", "of", "off", "on", "once",
    "only", "or", "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them", "themselves",
    "then", "there", "these", "they", "this", "those", "through", "to", "too", "under", "until",
    "up", "very", "was", "we", "were", "what", "when", "where", "which", "while", "who", "whom",
    "why", "with", "you", "your", "yours", "yourself", "yourselves",
])


class MockPolicyEncoder:
    """Offline mock policy encoder ensuring zero network/disk weight loading in mock profile.
    Uses deterministic stopword-filtered word vector sums for semantic similarity.
    """
    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.tokenizer = None

    def encode_passages(self, texts: List[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self.dimension), dtype=np.float32)
        vecs = []
        for t in texts:
            words = [w for w in re.findall(r"\w+", t.lower()) if w not in _STOPWORDS]
            if not words:
                words = re.findall(r"\w+", t.lower()) or ["empty"]
            v = np.zeros(self.dimension, dtype=np.float32)
            for w in words:
                h = int(hashlib.sha256(w.encode("utf-8")).hexdigest()[:8], 16)
                rng = np.random.RandomState(h)
                w_vec = rng.randn(self.dimension).astype(np.float32)
                v += w_vec / max(float(np.linalg.norm(w_vec)), 1e-6)
            norm = float(np.linalg.norm(v))
            vecs.append(v / (norm if norm > 0 else 1.0))
        return np.array(vecs, dtype=np.float32)

    def encode_queries(self, queries: List[str]) -> np.ndarray:
        return self.encode_passages(queries)

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode_passages([query])[0]


class MockLLMClient:
    """Zero-network mock LLM client completely isolated from environment keys and httpx."""
    def __init__(self, configured: bool = True):
        self.configured = configured

    def generate(self, question: str, intent: str, evidence: list[dict], business_context: dict | None = None) -> dict[str, Any]:
        if not self.configured:
            raise LLMError("llm_not_configured")
        citations = []
        body_parts = []
        for i, ev in enumerate(evidence[:3], start=1):
            doc_id = str(ev.get("document_id") or ev.get("doc_id", "DOC"))
            ver = str(ev.get("version", "1.0"))
            s_id = f"S{i}"
            citations.append({
                "source_id": s_id,
                "source_type": ev.get("source_type", "policy"),
                "document_id": doc_id,
                "version": ver,
            })
            excerpt = ev.get("excerpt") or ev.get("title") or "policy information"
            body_parts.extend(f"{sentence} [{s_id}]" for sentence in split_draft_sentences(excerpt.strip()))
        body = " ".join(body_parts) if body_parts else "Support information."
        return {
            "body": body,
            "citations": citations,
            "usage": {"input_tokens": 120, "output_tokens": 60},
        }


class MockIntentClient:
    """Offline mock intent classifier for zero-network benchmark runs."""
    def __init__(self, default_intent: str = "track_order"):
        self.default_intent = default_intent

    def classify_intent(self, text: str, request_id: Optional[str] = None):
        t_low = text.lower()
        if "close" in t_low and "account" in t_low:
            intent = "close_account"
        elif "return" in t_low or "refund" in t_low:
            intent = "return_policy"
        elif "ship" in t_low or "delivery" in t_low:
            intent = "shipping_costs"
        elif "track" in t_low or "order" in t_low:
            intent = "track_order"
        elif "cancel" in t_low:
            intent = "cancel_order"
        else:
            intent = self.default_intent

        return IntentPrediction(
            intent=intent,
            confidence=0.95,
            margin=0.30,
            model_version="v1.0-mock",
            score_kind="mock_softmax",
            error=None,
        )
