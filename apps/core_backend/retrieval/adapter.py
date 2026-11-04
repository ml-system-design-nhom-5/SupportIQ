import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

# Map intents to strictly required knowledge categories / rule prefixes
INTENT_CATEGORY_MAP = {
    "return_policy": {"return", "exchange"},
    "return_product": {"return", "exchange"},
    "refund_policy": {"refund"},
    "request_refund": {"refund"},
    "refund_status": {"refund"},
    "cancel_order": {"cancel", "cancellation"},
    "delivery_time": {"delivery", "shipping"},
    "delivery_issue": {"delivery", "shipping"},
    "shipping_costs": {"shipping", "freight"},
    "track_order": {"tracking", "order_tracking"},
    "payment_issue": {"payment", "billing"},
}

class RetrievalAdapter:
    """Semantic & policy retrieval adapter using approved and currently valid knowledge base documents."""
    def __init__(self, kb_path: Optional[str] = None):
        if kb_path:
            p = Path(kb_path)
        else:
            p = Path("data/knowledge/approved_kb.v1.json")
        self.documents: List[Dict[str, Any]] = []
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

    def retrieve(self, query: str, intent: str, current_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Retrieve relevant policy evidence snippets.
        Enforces:
        - Status must be 'approved'
        - Time validity: valid_from <= now <= valid_to
        - Strict relevance: document must match intent category/keywords specifically, avoiding generic false positives
        """
        if not self.documents:
            return {"status": "empty_kb", "evidence": []}

        now = current_time or datetime.now(timezone.utc)
        target_keywords = INTENT_CATEGORY_MAP.get(intent, {intent})
        matched_evidence = []

        for doc in self.documents:
            if doc.get("status") != "approved":
                continue

            # Check validity dates
            valid_from_str = doc.get("valid_from")
            valid_to_str = doc.get("valid_to")
            if valid_from_str:
                try:
                    v_from = datetime.fromisoformat(valid_from_str.replace("Z", "+00:00"))
                    if now < v_from:
                        continue
                except Exception:
                    pass

            if valid_to_str:
                try:
                    v_to = datetime.fromisoformat(valid_to_str.replace("Z", "+00:00"))
                    if now > v_to:
                        continue
                except Exception:
                    pass

            # Strict relevance matching: doc must contain specific intent keywords in policy_key, title, or category
            title = doc.get("title", "").lower()
            excerpt = doc.get("sanitized_excerpt", "").lower()
            doc_key = doc.get("policy_key", "").lower()

            doc_text = f"{title} {doc_key} {excerpt}"
            # Check if at least one specific intent keyword appears in document
            is_relevant = any(kw in doc_text for kw in target_keywords)

            if is_relevant:
                matched_evidence.append({
                    "document_id": doc.get("document_id"),
                    "title": doc.get("title"),
                    "excerpt": doc.get("sanitized_excerpt"),
                    "content_hash": doc.get("content_hash"),
                    "version": doc.get("version"),
                })

        if matched_evidence:
            return {"status": "success", "evidence": matched_evidence}
        return {"status": "no_match", "evidence": []}
