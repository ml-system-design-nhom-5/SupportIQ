import json
from pathlib import Path
from typing import Optional, List, Dict, Any

class RetrievalAdapter:
    """Semantic & policy retrieval adapter using approved knowledge base documents."""
    def __init__(self, kb_path: Optional[str] = None):
        if kb_path:
            p = Path(kb_path)
        else:
            p = Path("data/knowledge/approved_kb.v1.json")
        self.documents: List[Dict[str, Any]] = []
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

    def retrieve(self, query: str, intent: str) -> Dict[str, Any]:
        """Retrieve relevant policy evidence snippets. Returns status and evidence list."""
        if not self.documents:
            return {"status": "empty_kb", "evidence": []}

        matched_evidence = []
        q_lower = query.lower()
        for doc in self.documents:
            # Match by status and intent keywords
            if doc.get("status") == "approved":
                title = doc.get("title", "").lower()
                excerpt = doc.get("sanitized_excerpt", "").lower()
                doc_key = doc.get("policy_key", "").lower()

                # Basic relevance check
                if any(k in title or k in excerpt or k in doc_key for k in [intent.split("_")[0], "policy", "window"]):
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
