import pytest
import numpy as np
from datetime import datetime, timezone

from apps.core_backend.retrieval.importer import (
    PolicyDocument,
    PolicyMetadata,
    PolicyVersion,
    import_policies,
    eligible_versions,
    detect_rule_conflicts,
    conditions_overlap,
)
from apps.core_backend.retrieval.encoder import PolicyEncoder, chunk_policy
from apps.core_backend.retrieval.index import (
    SemanticPolicyIndex,
    search_policies,
    RetrievalResult,
)
from apps.core_backend.retrieval.adapter import RetrievalAdapter

def test_metadata_importer_valid_approved_passes():
    policies_data = [
        {
            "doc_id": "POL-TEST-001",
            "category": "return_refund",
            "title": "Standard Return",
            "content": "You can return items within 30 days.",
            "version": "1.0",
            "is_active": True,
            "tags": ["return"]
        }
    ]
    metadata_data = {
        "POL-TEST-001:1.0": {
            "status": "approved",
            "approved_by": "qa_lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["agent", "customer", "staff"],
            "policy_key": "return_window",
            "rule_assertions": [{"key": "return_window", "value": 30, "unit": "days", "condition": {"seller": "all"}}]
        }
    }
    report = import_policies(policies_data, metadata_data)
    assert report["imported_count"] == 1
    assert len(report["eligible"]) == 1
    assert report["quarantined_count"] == 0

    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    eligible = eligible_versions(report["eligible"], role="customer", as_of=now)
    assert len(eligible) == 1
    assert eligible[0].doc_id == "POL-TEST-001"


def test_metadata_importer_quarantines_missing_approval_fields():
    """P1: Missing mandatory approval fields (approved_by, approved_at, valid_from) quarantines the policy."""
    policies_data = [
        {
            "doc_id": "POL-NO-APPROVAL",
            "category": "misc",
            "title": "Unapproved",
            "content": "Content",
            "version": "1.0",
            "is_active": True,
        }
    ]
    metadata_data = {
        "POL-NO-APPROVAL:1.0": {
            "status": "approved",
            "allowed_roles": ["customer"]
        }
    }
    report = import_policies(policies_data, metadata_data)
    assert report["quarantined_count"] == 1
    assert "invalid_approval_metadata" in report["quarantined"][0]["reason"]


def test_conflict_detection_subset_conditions_overlap():
    """P2: {'seller':'X'} and {'seller':'X','market':'US'} overlap and conflict if values differ."""
    rules = [
        {"key": "return_window", "value": 30, "condition": {"seller": "X"}},
        {"key": "return_window", "value": 14, "condition": {"seller": "X", "market": "US"}},
    ]
    assert detect_rule_conflicts(rules) is True

    # Truly disjoint sellers do not conflict
    disjoint_rules = [
        {"key": "return_window", "value": 30, "condition": {"seller": "X"}},
        {"key": "return_window", "value": 14, "condition": {"seller": "Y"}},
    ]
    assert detect_rule_conflicts(disjoint_rules) is False


def test_encoder_raises_error_in_prod_mode_on_invalid_checkpoint():
    """P1: When model loading fails in production mode, raises RuntimeError instead of returning fake random vectors."""
    with pytest.raises(RuntimeError):
        PolicyEncoder(model_path="non_existent_bge_checkpoint_dir", mock_mode=False)


def test_pre_filtering_blocks_revoked_version_from_ranking():
    """P1: Chunks belonging to a revoked/disallowed version are filtered BEFORE ranking."""
    encoder = PolicyEncoder(mock_mode=True)
    chunks = [
        {"chunk_id": "P1:1.0:c0", "doc_id": "P1", "version": "1.0", "title": "P1 v1", "text": "P1 v1"},
        {"chunk_id": "P1:2.0:c0", "doc_id": "P1", "version": "2.0", "title": "P1 v2", "text": "P1 v2"},
    ]
    embeddings = encoder.encode_passages([c["text"] for c in chunks])
    index = SemanticPolicyIndex(chunks=chunks, embeddings=embeddings)

    allowed_keys = {("P1", "2.0")}
    result = search_policies(
        query="P1",
        index=index,
        encoder=encoder,
        threshold=-1.0,
        allowed_doc_version_keys=allowed_keys
    )
    assert result.status == "success"
    assert len(result.documents) == 1
    assert result.documents[0]["version"] == "2.0"


def test_token_budget_limits_selected_chunks():
    """P2: token_budget strictly stops selecting chunks when budget is exceeded."""
    encoder = PolicyEncoder(mock_mode=True)
    chunks = [
        {"chunk_id": "P1:1.0:c0", "doc_id": "P1", "version": "1.0", "title": "Doc 1", "text": "text", "token_count": 100},
        {"chunk_id": "P2:1.0:c0", "doc_id": "P2", "version": "1.0", "title": "Doc 2", "text": "text", "token_count": 100},
    ]
    embeddings = encoder.encode_passages([c["text"] for c in chunks])
    index = SemanticPolicyIndex(chunks=chunks, embeddings=embeddings)

    # Set budget to 150 tokens: should accept top ranked doc (100 tokens) and reject second doc (100+100 > 150)
    result = search_policies(
        query="text",
        index=index,
        encoder=encoder,
        threshold=-1.0,
        token_budget=150
    )
    assert result.status == "success"
    assert len(result.documents) == 1
    assert result.documents[0]["doc_id"] in ["P1", "P2"]
