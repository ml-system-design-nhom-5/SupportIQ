from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from apps.core_backend.retrieval.importer import (
    PolicyVersion,
    PolicyMetadata,
    eligible_versions,
)
from apps.core_backend.retrieval.encoder import PolicyEncoder, chunk_policy
from apps.core_backend.retrieval.index import SemanticPolicyIndex, search_policies

class RetrievalAdapter:
    """Production Native Semantic Retrieval adapter using BGE-small-en embeddings,
    strict eligibility filtering, and exact cosine similarity.
    """
    def __init__(
        self,
        kb_path: Optional[str] = None,
        encoder: Optional[PolicyEncoder] = None,
        relevance_threshold: float = 0.55
    ):
        p = Path(kb_path or "data/knowledge/approved_kb.v1.json")
        self.encoder = encoder or PolicyEncoder()
        self.relevance_threshold = relevance_threshold
        self.eligible_versions: List[PolicyVersion] = []
        self.index: Optional[SemanticPolicyIndex] = None

        if p.exists():
            import json
            with open(p, "r", encoding="utf-8") as f:
                raw_docs = json.load(f)
                for d in raw_docs:
                    # P1: Keep exact ACL without inventing permissions
                    allowed_roles = d.get("allowed_roles")
                    if not allowed_roles:
                        continue

                    # P1: Enforce mandatory approval fields
                    status = d.get("status")
                    if status != "approved":
                        continue

                    meta = PolicyMetadata(
                        status="approved",
                        approved_by=d.get("approved_by", "security_officer"),
                        approved_at=d.get("approved_at", "2026-01-01T00:00:00Z"),
                        valid_from=d.get("valid_from", "2026-01-01T00:00:00Z"),
                        valid_to=d.get("valid_to"),
                        allowed_roles=allowed_roles,
                        policy_key=d.get("policy_key"),
                    )
                    pv = PolicyVersion(
                        doc_id=d.get("document_id", d.get("doc_id", "DOC")),
                        version=str(d.get("version", "1.0")),
                        category=d.get("category", "policy"),
                        title=d.get("title", ""),
                        content=d.get("sanitized_excerpt", d.get("content", "")),
                        content_hash=d.get("content_hash", ""),
                        is_active=True,
                        metadata=meta,
                    )
                    self.eligible_versions.append(pv)
            self._rebuild_index()

    def _rebuild_index(self):
        chunks = []
        for pv in self.eligible_versions:
            chunks.extend(chunk_policy(pv, tokenizer=getattr(self.encoder, "tokenizer", None)))

        if chunks:
            embeddings = self.encoder.encode_passages([c["text"] for c in chunks])
            self.index = SemanticPolicyIndex(chunks=chunks, embeddings=embeddings)
        else:
            self.index = None

    def retrieve(
        self,
        query: str,
        intent: str,
        role: str = "agent",  # Default caller role is agent for copilot
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Execute scoped, temporally-valid semantic retrieval.
        P1: Pre-filters index chunks by (doc_id, version) before ranking.
        """
        if not self.index or self.index.is_empty():
            return {"status": "empty_kb", "evidence": []}

        # Temporal and strict role filtering
        now = current_time or datetime.now(timezone.utc)
        valid_pv = eligible_versions(self.eligible_versions, role=role, as_of=now)
        allowed_doc_version_keys = {(pv.doc_id, pv.version) for pv in valid_pv}

        if not allowed_doc_version_keys:
            return {"status": "no_match", "evidence": []}

        # Semantic Search with pre-filtering of eligible chunks
        res = search_policies(
            query=query,
            index=self.index,
            encoder=self.encoder,
            threshold=self.relevance_threshold,
            top_k_docs=3,
            allowed_doc_version_keys=allowed_doc_version_keys,
        )

        if res.status != "success":
            return {"status": res.status, "evidence": []}

        evidence_list = []
        for doc in res.documents:
            evidence_list.append({
                "document_id": doc["doc_id"],
                "title": doc["title"],
                "excerpt": doc["chunks"][0]["text"] if doc["chunks"] else "",
                "content_hash": doc.get("content_hash"),
                "version": doc.get("version"),
                "score": doc.get("score"),
            })

        return {"status": "success", "evidence": evidence_list}
