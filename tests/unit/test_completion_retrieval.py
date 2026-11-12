"""Unit tests for semantic retrieval applicability filtering, capability checks, and version integrity (Task 4)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.core_backend.retrieval.adapter import RetrievalAdapter
from apps.core_backend.retrieval.importer import PolicyMetadata, PolicyVersion
from pipeline.evaluation.system_execution import MockPolicyEncoder


@pytest.fixture
def knowledge_base_v2(tmp_path):
    kb_file = tmp_path / "approved_kb.v2.json"
    data = [
        {
            "doc_id": "POL-RET-001",
            "document_id": "POL-RET-001",
            "version": "2.0",
            "status": "approved",
            "approved_by": "lead_compliance",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer"],
            "title": "Return Policy Window and Conditions",
            "content": "Return items within 30 days in original packaging.",
            "content_hash": hashlib.sha256("Return items within 30 days in original packaging.".encode("utf-8")).hexdigest(),
            "supported_intents": ["return_policy", "return_product"],
            "answer_capabilities": ["return_window", "return_conditions"],
        },
        {
            "doc_id": "POL-RET-002",
            "document_id": "POL-RET-002",
            "version": "2.0",
            "status": "approved",
            "approved_by": "lead_compliance",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer"],
            "title": "Return Initiation Steps on App",
            "content": "To request a return, go to Orders > tap Request Return and upload photos.",
            "content_hash": hashlib.sha256("To request a return, go to Orders > tap Request Return and upload photos.".encode("utf-8")).hexdigest(),
            "supported_intents": ["return_product"],
            "answer_capabilities": ["return_initiation", "return_instructions"],
        },
        {
            "doc_id": "POL-ORD-002",
            "document_id": "POL-ORD-002",
            "version": "2.0",
            "status": "approved",
            "approved_by": "lead_compliance",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer"],
            "title": "Order Cancellation Policy",
            "content": "Orders may be cancelled before shipment fulfillment without fee.",
            "content_hash": hashlib.sha256("Orders may be cancelled before shipment fulfillment without fee.".encode("utf-8")).hexdigest(),
            "supported_intents": ["cancel_order"],
            "answer_capabilities": ["cancellation_window", "cancel_unfulfilled"],
        },
        {
            "doc_id": "POL-REFUND-002",
            "document_id": "POL-REFUND-002",
            "version": "2.0",
            "status": "approved",
            "approved_by": "lead_compliance",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer"],
            "title": "Refund Receipt Timeline",
            "content": "Refunds are processed within 5-7 business days to your original payment method.",
            "content_hash": hashlib.sha256("Refunds are processed within 5-7 business days to your original payment method.".encode("utf-8")).hexdigest(),
            "supported_intents": ["refund_policy", "refund_status"],
            "answer_capabilities": ["refund_timeline", "payment_method_timelines"],
        },
        {
            "doc_id": "POL-EXPIRED-01",
            "document_id": "POL-EXPIRED-01",
            "version": "1.0",
            "status": "approved",
            "approved_by": "lead_compliance",
            "approved_at": "2025-01-01T00:00:00Z",
            "valid_from": "2025-01-01T00:00:00Z",
            "valid_to": "2025-12-31T23:59:59Z",  # Expired
            "allowed_roles": ["agent", "customer"],
            "title": "Expired Policy",
            "content": "Expired refund rules.",
            "content_hash": hashlib.sha256("Expired refund rules.".encode("utf-8")).hexdigest(),
            "supported_intents": ["refund_policy"],
            "answer_capabilities": ["refund_timeline"],
        },
    ]
    kb_file.write_text(json.dumps(data), encoding="utf-8")
    return kb_file


class TestSemanticRetrievalRelevanceAndCapabilities:
    def test_refund_query_does_not_accept_cancellation_policy(self, knowledge_base_v2):
        """A refund query must never return a cancellation policy document as answer evidence."""
        adapter = RetrievalAdapter(kb_path=str(knowledge_base_v2), encoder=MockPolicyEncoder(), relevance_threshold=0.0)
        res = adapter.retrieve(
            query="Can I get a refund for my item?",
            intent="refund_policy",
            role="agent",
            current_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        assert res["status"] == "success"
        retrieved_ids = [e["document_id"] for e in res["evidence"]]
        assert "POL-ORD-002" not in retrieved_ids, "Cancellation policy leaked into refund query!"
        assert "POL-REFUND-002" in retrieved_ids

    def test_return_initiation_requires_instructions_capability(self, knowledge_base_v2):
        """Inquiry asking how to initiate a return must match return_initiation capability."""
        adapter = RetrievalAdapter(kb_path=str(knowledge_base_v2), encoder=MockPolicyEncoder(), relevance_threshold=0.0)
        res = adapter.retrieve(
            query="How do I submit a return request on the app?",
            intent="return_product",
            role="agent",
            current_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        assert res["status"] == "success"
        retrieved_ids = [e["document_id"] for e in res["evidence"]]
        assert "POL-RET-002" in retrieved_ids

    def test_expired_or_revoked_documents_are_never_retrieved(self, knowledge_base_v2):
        """Expired document POL-EXPIRED-01 must never be returned for an as_of date in 2026."""
        adapter = RetrievalAdapter(kb_path=str(knowledge_base_v2), encoder=MockPolicyEncoder(), relevance_threshold=0.0)
        res = adapter.retrieve(
            query="What are the refund rules?",
            intent="refund_policy",
            role="agent",
            current_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        retrieved_ids = [e["document_id"] for e in res["evidence"]]
        assert "POL-EXPIRED-01" not in retrieved_ids, "Expired document was retrieved!"

    def test_evidence_payload_contains_required_fields(self, knowledge_base_v2):
        """Evidence returned by retrieve must include source_type, excerpt, version, and content_hash."""
        adapter = RetrievalAdapter(kb_path=str(knowledge_base_v2), encoder=MockPolicyEncoder(), relevance_threshold=0.0)
        res = adapter.retrieve(
            query="When can I return?",
            intent="return_policy",
            role="agent",
            current_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        assert res["status"] == "success"
        assert len(res["evidence"]) > 0
        ev = res["evidence"][0]
        assert ev.get("source_type") == "policy"
        assert ev.get("document_id") == "POL-RET-001"
        assert ev.get("version") == "2.0"
        assert ev.get("content_hash") is not None
        assert ev.get("excerpt") is not None
