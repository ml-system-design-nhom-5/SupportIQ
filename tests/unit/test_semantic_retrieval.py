from datetime import datetime, timezone
import numpy as np
import pytest
from apps.core_backend.retrieval.importer import (
    PolicyDocument,
    PolicyMetadata,
    PolicyVersion,
    import_policies,
    eligible_versions,
    detect_rule_conflicts,
)
from apps.core_backend.retrieval.encoder import PolicyEncoder, chunk_policy
from apps.core_backend.retrieval.index import (
    SemanticPolicyIndex,
    search_policies,
    RetrievalResult,
)

def test_metadata_importer_valid_approved_passes(tmp_path):
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
            "rule_assertions": [{"key": "return_window", "value": 30, "unit": "days", "condition": "all"}]
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


def test_metadata_importer_excludes_inactive_or_expired():
    policies_data = [
        {
            "doc_id": "POL-INACT-001",
            "category": "return_refund",
            "title": "Inactive policy",
            "content": "Old rules",
            "version": "1.0",
            "is_active": False,
            "tags": []
        },
        {
            "doc_id": "POL-EXP-002",
            "category": "return_refund",
            "title": "Expired policy",
            "content": "Expired rules",
            "version": "1.0",
            "is_active": True,
            "tags": []
        }
    ]
    metadata_data = {
        "POL-INACT-001:1.0": {
            "status": "approved",
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["customer"]
        },
        "POL-EXP-002:1.0": {
            "status": "approved",
            "valid_from": "2025-01-01T00:00:00Z",
            "valid_to": "2025-12-31T23:59:59Z",
            "allowed_roles": ["customer"]
        }
    }
    report = import_policies(policies_data, metadata_data)
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    eligible = eligible_versions(report["eligible"], role="customer", as_of=now)
    assert len(eligible) == 0


def test_conflict_detection_overlapping_conditions():
    rules = [
        {"key": "return_window", "value": 30, "condition": {"seller": "tiki_trading"}},
        {"key": "return_window", "value": 7, "condition": {"seller": "marketplace"}},
    ]
    assert detect_rule_conflicts(rules) is False

    conflicting_rules = [
        {"key": "return_window", "value": 30, "condition": {"seller": "tiki_trading"}},
        {"key": "return_window", "value": 14, "condition": {"seller": "tiki_trading"}},
    ]
    assert detect_rule_conflicts(conflicting_rules) is True


def test_chunking_short_policy_creates_single_chunk():
    policy = PolicyVersion(
        doc_id="POL-001",
        version="1.0",
        category="shipping",
        title="Delivery Hours",
        content="We deliver from 8am to 5pm Monday to Friday.",
        content_hash="hash1",
        is_active=True,
        metadata=PolicyMetadata()
    )
    chunks = chunk_policy(policy, max_tokens=480, overlap=40)
    assert len(chunks) == 1
    assert chunks[0]["doc_id"] == "POL-001"
    assert "Delivery Hours" in chunks[0]["text"]


def test_encoder_normalizes_embeddings_to_unit_length():
    encoder = PolicyEncoder(mock_mode=True)
    embeddings = encoder.encode_queries(["How long does shipping take?"])
    assert embeddings.shape == (1, 384)
    norm = np.linalg.norm(embeddings[0])
    assert abs(norm - 1.0) < 1e-5


def test_cosine_ranking_returns_top3_distinct_documents():
    """Verify semantic search returns up to 3 distinct documents, grouping multiple chunks per document."""
    encoder = PolicyEncoder(mock_mode=True)
    chunks = [
        {"chunk_id": "P1:1:c0", "doc_id": "P1", "version": "1.0", "title": "Doc 1 Chunk 0", "text": "Doc 1 Chunk 0", "category": "return"},
        {"chunk_id": "P1:1:c1", "doc_id": "P1", "version": "1.0", "title": "Doc 1 Chunk 1", "text": "Doc 1 Chunk 1", "category": "return"},
        {"chunk_id": "P2:1:c0", "doc_id": "P2", "version": "1.0", "title": "Doc 2 Chunk 0", "text": "Doc 2 Chunk 0", "category": "refund"},
        {"chunk_id": "P3:1:c0", "doc_id": "P3", "version": "1.0", "title": "Doc 3 Chunk 0", "text": "Doc 3 Chunk 0", "category": "cancel"},
        {"chunk_id": "P4:1:c0", "doc_id": "P4", "version": "1.0", "title": "Doc 4 Chunk 0", "text": "Doc 4 Chunk 0", "category": "shipping"},
    ]
    # Build embeddings
    embeddings = encoder.encode_passages([c["text"] for c in chunks])
    index = SemanticPolicyIndex(chunks=chunks, embeddings=embeddings)

    result = search_policies(
        query="I want to return an item",
        index=index,
        encoder=encoder,
        threshold=0.0  # Accept all for this toy test
    )
    assert result.status == "success"
    assert len(result.documents) <= 3
    # Check distinct doc_ids
    doc_ids = [d["doc_id"] for d in result.documents]
    assert len(doc_ids) == len(set(doc_ids))


def test_relevance_threshold_gate_rejects_low_similarity():
    """Relevance gate: if highest similarity is below threshold, returns no_evidence."""
    encoder = PolicyEncoder(mock_mode=True)
    chunks = [
        {"chunk_id": "P1:1:c0", "doc_id": "P1", "version": "1.0", "title": "Doc 1", "text": "Unrelated topic", "category": "misc"}
    ]
    embeddings = encoder.encode_passages([c["text"] for c in chunks])
    index = SemanticPolicyIndex(chunks=chunks, embeddings=embeddings)

    # Set threshold very high (0.9999) to force rejection
    result = search_policies(
        query="Some query",
        index=index,
        encoder=encoder,
        threshold=0.9999
    )
    assert result.status == "no_evidence"
    assert len(result.documents) == 0
