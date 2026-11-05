"""Unit tests for Knowledge Base completeness, metadata validation, and publishing (Task 3)."""

import hashlib
import json
from pathlib import Path

import pytest

from apps.core_backend.retrieval.importer import (
    PolicyMetadata,
    PolicyVersion,
    detect_rule_conflicts,
    eligible_versions,
    import_policies,
    publish_approved_kb,
)
from apps.core_backend.retrieval.adapter import RetrievalAdapter


class TestPolicyMetadataValidation:
    def test_missing_or_unapproved_status_quarantined(self):
        """Documents lacking explicit approved status must be quarantined."""
        policies = [{
            "doc_id": "POL-TEST-01",
            "version": "1.0",
            "content": "Return within 30 days.",
            "is_active": True,
        }]
        # Metadata with status="draft"
        metadata = {
            "POL-TEST-01:1.0": {
                "status": "draft",
                "approved_by": "compliance_lead",
                "approved_at": "2026-01-01T00:00:00Z",
                "valid_from": "2026-01-01T00:00:00Z",
                "allowed_roles": ["agent", "customer"],
            }
        }
        res = import_policies(policies, metadata)
        assert res["quarantined_count"] == 1
        assert len(res["eligible"]) == 0

    def test_empty_or_invalid_acl_roles_rejected(self):
        """Empty allowed_roles or invalid roles must raise validation error and be quarantined."""
        with pytest.raises(Exception):
            PolicyMetadata(
                status="approved",
                approved_by="compliance_lead",
                approved_at="2026-01-01T00:00:00Z",
                valid_from="2026-01-01T00:00:00Z",
                allowed_roles=[],  # Empty ACL
            )

        with pytest.raises(Exception):
            PolicyMetadata(
                status="approved",
                approved_by="compliance_lead",
                approved_at="2026-01-01T00:00:00Z",
                valid_from="2026-01-01T00:00:00Z",
                allowed_roles=["superuser_unauthorized"],  # Invalid role
            )

    def test_supported_intents_and_answer_capabilities_fields(self):
        """PolicyMetadata supports applicability metadata fields supported_intents and answer_capabilities."""
        meta = PolicyMetadata(
            status="approved",
            approved_by="compliance_lead",
            approved_at="2026-01-01T00:00:00Z",
            valid_from="2026-01-01T00:00:00Z",
            allowed_roles=["agent", "customer"],
            supported_intents=["return_policy"],
            answer_capabilities=["return_window", "return_conditions"],
        )
        assert meta.supported_intents == ["return_policy"]
        assert "return_window" in meta.answer_capabilities

    def test_conflicting_rule_assertions_detected(self):
        """Overlapping conditions with contradictory values must be flagged as conflict."""
        rules = [
            {"key": "return_fee", "condition": "all", "value": "free"},
            {"key": "return_fee", "condition": {}, "value": "$5.00"},
        ]
        assert detect_rule_conflicts(rules) is True


class TestPublishApprovedKB:
    def test_publish_approved_kb_refuses_existing_version(self, tmp_path):
        """publish_approved_kb must refuse to overwrite an existing published version file."""
        staging_file = tmp_path / "staging.json"
        staging_data = [{
            "doc_id": "KB-01",
            "document_id": "KB-01",
            "title": "Return Policy",
            "version": "2.0",
            "status": "approved",
            "approved_by": "compliance_lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "allowed_roles": ["agent", "customer"],
            "content": "Return items within 30 days.",
            "content_hash": hashlib.sha256("Return items within 30 days.".encode("utf-8")).hexdigest(),
            "supported_intents": ["return_policy"],
            "answer_capabilities": ["return_window"],
        }]
        staging_file.write_text(json.dumps(staging_data), encoding="utf-8")

        output_file = tmp_path / "approved_kb.v2.json"
        output_file.write_text("existing content", encoding="utf-8")

        with pytest.raises(FileExistsError, match="Refusing to overwrite"):
            publish_approved_kb(staging_file, output_file)

    def test_publish_approved_kb_rejects_placeholder_hash(self, tmp_path):
        """publish_approved_kb must reject documents with placeholder or mismatched content hash."""
        staging_file = tmp_path / "staging_bad_hash.json"
        staging_data = [{
            "doc_id": "KB-01",
            "document_id": "KB-01",
            "title": "Return Policy",
            "version": "2.0",
            "status": "approved",
            "approved_by": "compliance_lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "allowed_roles": ["agent", "customer"],
            "content": "Return items within 30 days.",
            "content_hash": "placeholder_dummy_hash",
            "supported_intents": ["return_policy"],
            "answer_capabilities": ["return_window"],
        }]
        staging_file.write_text(json.dumps(staging_data), encoding="utf-8")
        output_file = tmp_path / "out_bad_hash.json"

        with pytest.raises(ValueError, match="content hash mismatch"):
            publish_approved_kb(staging_file, output_file)

    def test_publish_approved_kb_publishes_verified_data(self, tmp_path):
        """Valid staging records are verified, published, and can be loaded by RetrievalAdapter."""
        content = "Standard return policy allows returns within 30 days."
        real_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        staging_file = tmp_path / "staging_valid.json"
        staging_data = [{
            "doc_id": "KB-RET-01",
            "document_id": "KB-RET-01",
            "title": "Standard Return Policy",
            "version": "2.0",
            "status": "approved",
            "approved_by": "lead_compliance",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer"],
            "content": content,
            "content_hash": real_hash,
            "supported_intents": ["return_policy"],
            "answer_capabilities": ["return_window", "return_conditions"],
        }]
        staging_file.write_text(json.dumps(staging_data), encoding="utf-8")
        output_file = tmp_path / "published_kb.v2.json"

        pub_path = publish_approved_kb(staging_file, output_file)
        assert pub_path.exists()

        # Load with mock encoder in RetrievalAdapter
        from pipeline.evaluation.system_execution import MockPolicyEncoder
        adapter = RetrievalAdapter(kb_path=str(pub_path), encoder=MockPolicyEncoder())
        assert len(adapter.eligible_versions) == 1
        pv = adapter.eligible_versions[0]
        assert pv.doc_id == "KB-RET-01"
        assert pv.metadata.supported_intents == ["return_policy"]
        assert "return_window" in pv.metadata.answer_capabilities
