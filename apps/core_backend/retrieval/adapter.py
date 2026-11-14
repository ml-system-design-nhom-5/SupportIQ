from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
import re

from apps.core_backend.retrieval.importer import (
    PolicyVersion,
    PolicyMetadata,
    eligible_versions,
)
from apps.core_backend.retrieval.encoder import PolicyEncoder, chunk_policy
from apps.core_backend.retrieval.index import SemanticPolicyIndex, search_policies

logger = logging.getLogger("retrieval_adapter")

BOUNDED_RETRIEVAL_REASON_CODES = frozenset({
    "encoder_unavailable",
    "encoder_failure",
    "encoder_failed",
    "empty_kb",
    "empty_index",
    "no_eligible_chunks",
    "no_match",
    "no_evidence",
    "below_relevance_threshold",
    "token_budget_exceeded",
    "no_chunks",
    "only_expired_documents",
    "insufficient_evidence",
})


def _filter_bounded_reasons(codes: Optional[List[str]]) -> List[str]:
    if not codes:
        return []
    return list(dict.fromkeys(c for c in codes if isinstance(c, str) and c in BOUNDED_RETRIEVAL_REASON_CODES))


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
        relevance_threshold: float = 0.55,
        allowed_document_versions: Optional[set[tuple[str, str]]] = None,
    ):
        p = Path(kb_path or "data/knowledge/approved_kb.v2.json")
        self.encoder = encoder
        self.encoder_error: Optional[str] = None
        if self.encoder is None:
            try:
                self.encoder = PolicyEncoder()
            except Exception as e:
                # Store only exception class name privately; never expose raw exception text or credentials.
                logger.warning("Retrieval encoder could not be initialized (%s)", type(e).__name__)
                self.encoder = None
                self.encoder_error = type(e).__name__

        self.relevance_threshold = relevance_threshold
        self.eligible_versions: List[PolicyVersion] = []
        self.quarantined_docs: List[Dict[str, Any]] = []
        self.index: Optional[SemanticPolicyIndex] = None

        if p.exists():
            import json
            with open(p, "r", encoding="utf-8") as f:
                raw_docs = json.load(f)
                for d in raw_docs:
                    key = (d.get("document_id", d.get("doc_id")), str(d.get("version")))
                    if allowed_document_versions is not None and key not in allowed_document_versions:
                        self.quarantined_docs.append({"document_id": key[0], "reason": "not_in_current_release"})
                        continue
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
                    except Exception:
                        self.quarantined_docs.append({
                            "document_id": d.get("document_id"),
                            "reason": "invalid_approval_metadata",
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
            return {
                "status": "encoder_unavailable",
                "evidence": [],
                "reason_codes": ["encoder_unavailable"],
                "has_conflict": False,
            }

        if intent == "human_agent":
            return {"status": "human_agent_escalation", "evidence": [], "reason_codes": [], "has_conflict": False}

        if not self.index or self.index.is_empty():
            return {"status": "empty_kb", "evidence": [], "reason_codes": ["empty_kb"], "has_conflict": False}

        # Temporal and strict role filtering
        now = current_time or datetime.now(timezone.utc)
        valid_pv = eligible_versions(self.eligible_versions, role=role, as_of=now)

        # ADR-0005: Retrieval uses message content only across all valid policies
        allowed_doc_version_keys = {(pv.doc_id, pv.version) for pv in valid_pv}

        if not allowed_doc_version_keys:
            return {"status": "no_match", "evidence": [], "reason_codes": ["no_match"], "has_conflict": False}

        # Semantic Search across all temporally valid documents
        try:
            res = search_policies(
                query=query,
                index=self.index,
                encoder=self.encoder,
                threshold=self.relevance_threshold,
                top_k_docs=3,
                allowed_doc_version_keys=allowed_doc_version_keys,
            )
        except Exception as exc:
            logger.warning("Retrieval query encoding failed (%s)", type(exc).__name__)
            return {
                "status": "encoder_failure",
                "evidence": [],
                "reason_codes": ["encoder_failure", "encoder_failed"],
                "has_conflict": False,
            }

        raw_codes = list(res.reason_codes or [])
        if res.status == "error" or "encoder_failed" in raw_codes or "encoder_failure" in raw_codes:
            logger.warning("Retrieval query encoding failed (bounded_status=%s)", res.status)
            return {
                "status": "encoder_failure",
                "evidence": [],
                "reason_codes": ["encoder_failure", "encoder_failed"],
                "has_conflict": False,
            }

        if res.status != "success":
            return {
                "status": res.status,
                "evidence": [],
                "reason_codes": _filter_bounded_reasons(raw_codes),
                "has_conflict": False,
            }

        pv_by_key = {(pv.doc_id, pv.version): pv for pv in valid_pv}

        # ADR-0005: Additive intent-aware reranking
        LAMBDA_INTENT = 0.15
        reranked_docs = []
        is_unauthorized_query = bool(re.search(r"\b(chargeback|unauthorized\s+(?:transaction|payment|charge)|fraud)\b", query, re.I))
        for doc in res.documents:
            pv = pv_by_key.get((doc["doc_id"], doc.get("version")))
            # When the customer reports unauthorized charge or chargeback, duplicate charge resolution (POL-PAY-004) is inapplicable
            if is_unauthorized_query and pv and "duplicate_charge_resolution" in pv.metadata.answer_capabilities:
                continue
            base_score = float(doc.get("score") or 0.0)
            boost = LAMBDA_INTENT if (intent and pv and (not pv.metadata.supported_intents or intent in pv.metadata.supported_intents)) else 0.0
            doc["score"] = round(base_score + boost, 4)
            reranked_docs.append(doc)

        reranked_docs.sort(key=lambda d: d.get("score") or 0.0, reverse=True)

        # Check for policy conflicts (e.g. multiple distinct versions of the same policy key)
        retrieved_keys = [
            pv_by_key[(d["doc_id"], d.get("version"))].metadata.policy_key
            for d in reranked_docs
            if (d["doc_id"], d.get("version")) in pv_by_key and pv_by_key[(d["doc_id"], d.get("version"))].metadata.policy_key
        ]
        has_conflict = len(retrieved_keys) > 1 and len(retrieved_keys) != len(set(retrieved_keys))

        evidence_list = []
        for doc in reranked_docs:
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

        return {"status": "success", "evidence": evidence_list, "has_conflict": has_conflict}
