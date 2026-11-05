from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

from apps.core_backend.retrieval.importer import (
    PolicyVersion,
    PolicyMetadata,
    eligible_versions,
)
from apps.core_backend.retrieval.encoder import PolicyEncoder, chunk_policy
from apps.core_backend.retrieval.index import SemanticPolicyIndex, search_policies

logger = logging.getLogger("retrieval_adapter")

class RetrievalAdapter:
    """Production Native Semantic Retrieval adapter using BGE-small-en embeddings,
    strict eligibility filtering, and exact cosine similarity.
    P1 FIX: Does NOT fabricate missing approval metadata; documents missing mandatory
    fields are quarantined and excluded.
    """
    def __init__(
        self,
        kb_path: Optional[str] = None,
        encoder: Optional[PolicyEncoder] = None,
        relevance_threshold: float = 0.55
    ):
        p = Path(kb_path or "data/knowledge/approved_kb.v2.json")
        self.encoder = encoder
        self.encoder_error: Optional[str] = None
        if self.encoder is None:
            try:
                self.encoder = PolicyEncoder()
            except Exception as e:
                # P1 FIX: Capture encoder initialization error gracefully at adapter boundary
                logger.warning(f"Retrieval encoder could not be initialized: {e}")
                self.encoder = None
                self.encoder_error = str(e)

        self.relevance_threshold = relevance_threshold
        self.eligible_versions: List[PolicyVersion] = []
        self.quarantined_docs: List[Dict[str, Any]] = []
        self.index: Optional[SemanticPolicyIndex] = None

        if p.exists():
            import json
            with open(p, "r", encoding="utf-8") as f:
                raw_docs = json.load(f)
                for d in raw_docs:
                    # P1: Strict validation - do NOT invent missing approval metadata
                    status = d.get("status")
                    approved_by = d.get("approved_by")
                    approved_at = d.get("approved_at")
                    valid_from = d.get("valid_from")
                    allowed_roles = d.get("allowed_roles")

                    if not (status == "approved" and approved_by and approved_at and valid_from and allowed_roles):
                        self.quarantined_docs.append({
                            "document_id": d.get("document_id"),
                            "reason": "missing_mandatory_approval_metadata"
                        })
                        continue

                    try:
                        meta = PolicyMetadata(
                            status="approved",
                            approved_by=approved_by,
                            approved_at=approved_at,
                            valid_from=valid_from,
                            valid_to=d.get("valid_to"),
                            allowed_roles=allowed_roles,
                            policy_key=d.get("policy_key"),
                            supported_intents=d.get("supported_intents", []),
                            answer_capabilities=d.get("answer_capabilities", []),
                        )
                    except Exception as e:
                        self.quarantined_docs.append({
                            "document_id": d.get("document_id"),
                            "reason": f"invalid_approval_metadata: {e}"
                        })
                        continue

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
        if not self.encoder:
            self.index = None
            return

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
        if self.encoder is None:
            return {"status": "encoder_unavailable", "evidence": [], "error": self.encoder_error}

        if not self.index or self.index.is_empty():
            return {"status": "empty_kb", "evidence": []}

        # Temporal and strict role filtering
        now = current_time or datetime.now(timezone.utc)
        valid_pv = eligible_versions(self.eligible_versions, role=role, as_of=now)

        # Pre-filter by applicability: if a policy document specifies supported_intents, it must match intent
        if intent:
            applicable_pv = [
                pv for pv in valid_pv
                if not pv.metadata.supported_intents or intent in pv.metadata.supported_intents
            ]
        else:
            applicable_pv = valid_pv

        allowed_doc_version_keys = {(pv.doc_id, pv.version) for pv in applicable_pv}

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

        pv_by_key = {(pv.doc_id, pv.version): pv for pv in applicable_pv}
        evidence_list = []
        for doc in res.documents:
            pv = pv_by_key.get((doc["doc_id"], doc.get("version")))
            chunk_ids = [c.get("chunk_id") for c in doc.get("chunks", []) if c.get("chunk_id")]
            capabilities = pv.metadata.answer_capabilities if pv else []
            evidence_list.append({
                "source_type": "policy",
                "document_id": doc["doc_id"],
                "doc_id": doc["doc_id"],
                "title": doc["title"],
                "excerpt": doc["chunks"][0]["text"] if doc["chunks"] else "",
                "chunk_ids": chunk_ids,
                "content_hash": doc.get("content_hash"),
                "version": doc.get("version"),
                "score": doc.get("score"),
                "capabilities": capabilities,
            })

        return {"status": "success", "evidence": evidence_list}
