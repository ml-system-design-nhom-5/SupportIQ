from datetime import datetime, timezone
import pytest

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


def test_metadata_importer_quarantines_missing_approval_fields():
    """Missing mandatory approval fields (approved_by, approved_at, valid_from) quarantines the policy."""
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


def test_malformed_date_is_rejected_and_quarantined():
    """P1: Malformed dates in valid_from or valid_to must quarantine the policy, and eligible_versions must exclude bad dates."""
    policies_data = [
        {
            "doc_id": "POL-BAD-DATE",
            "category": "misc",
            "title": "Bad Date Policy",
            "content": "Content",
            "version": "1.0",
            "is_active": True,
        }
    ]
    metadata_data = {
        "POL-BAD-DATE:1.0": {
            "status": "approved",
            "approved_by": "lead",
            "approved_at": "2026-01-01T00:00:00Z",
            "valid_from": "bad-date-not-iso",
            "valid_to": "2026-12-31T23:59:59Z",
            "allowed_roles": ["customer"],
        }
    }
    report = import_policies(policies_data, metadata_data)
    assert report["quarantined_count"] == 1
    assert "invalid_approval_metadata" in report["quarantined"][0]["reason"]

    # Even if constructed directly with unvalidated dict, eligible_versions excludes unverifiable dates
    meta = PolicyMetadata.model_construct(
        status="approved",
        approved_by="lead",
        approved_at="2026-01-01T00:00:00Z",
        valid_from="bad-date",
        valid_to="2026-12-31T23:59:59Z",
        allowed_roles=["customer"],
    )
    pv = PolicyVersion(
        doc_id="POL-BAD",
        version="1.0",
        category="misc",
        title="Title",
        content="Content",
        content_hash="hash",
        is_active=True,
        metadata=meta,
    )
    now = datetime(2026, 6, 1, tzinfo=timezone.utc)
    res = eligible_versions([pv], role="customer", as_of=now)
    assert len(res) == 0


def test_boundary_expiry_excludes_at_exact_expiration_timestamp():
    """P2: Policy is valid strictly for valid_from <= as_of < valid_to. At now == valid_to, it must be excluded!"""
    expiry_str = "2026-12-31T23:59:59Z"
    meta = PolicyMetadata(
        status="approved",
        approved_by="lead",
        approved_at="2026-01-01T00:00:00Z",
        valid_from="2026-01-01T00:00:00Z",
        valid_to=expiry_str,
        allowed_roles=["customer"],
    )
    pv = PolicyVersion(
        doc_id="POL-EXPIRY-TEST",
        version="1.0",
        category="misc",
        title="Title",
        content="Content",
        content_hash="hash",
        is_active=True,
        metadata=meta,
    )

    # 1 second before expiration -> valid
    before_expiry = datetime(2026, 12, 31, 23, 59, 58, tzinfo=timezone.utc)
    assert len(eligible_versions([pv], role="customer", as_of=before_expiry)) == 1

    # Exactly AT expiration timestamp -> EXCLUDED (P2 fix)
    at_expiry = datetime(2026, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    assert len(eligible_versions([pv], role="customer", as_of=at_expiry)) == 0

    # After expiration -> EXCLUDED
    after_expiry = datetime(2027, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    assert len(eligible_versions([pv], role="customer", as_of=after_expiry)) == 0


def test_conflict_detection_handles_universal_condition_all():
    rules = [
        {"key": "return_window", "value": 30, "condition": "all"},
        {"key": "return_window", "value": 14, "condition": {"seller": "X"}},
    ]
    assert detect_rule_conflicts(rules) is True

    no_conflict_rules = [
        {"key": "return_window", "value": 30, "condition": "all"},
        {"key": "return_window", "value": 30, "condition": {"seller": "X"}},
    ]
    assert detect_rule_conflicts(no_conflict_rules) is False


def test_adapter_fails_closed_and_quarantines_unapproved_documents(tmp_path):
    bad_kb_file = tmp_path / "bad_kb.json"
    import json
    bad_kb_file.write_text(json.dumps([
        {
            "document_id": "DOC-UNAPPROVED",
            "status": "approved",
            "allowed_roles": ["agent"],
            "sanitized_excerpt": "Text"
        }
    ]), encoding="utf-8")

    encoder = PolicyEncoder(mock_mode=True)
    adapter = RetrievalAdapter(kb_path=str(bad_kb_file), encoder=encoder)
    assert len(adapter.eligible_versions) == 0
    assert len(adapter.quarantined_docs) == 1
    assert adapter.quarantined_docs[0]["reason"] == "missing_mandatory_approval_metadata"

    res = adapter.retrieve("Text", "policy", role="agent")
    assert res["status"] == "empty_kb"


def test_orchestration_boundary_handles_encoder_failure_gracefully(tmp_path, offline_retrieval):
    from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
    from apps.core_backend.orchestration.store import PersistentStore
    from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction

    adapter = offline_retrieval
    adapter.encoder = None
    adapter.encoder_error = "Mocked checkpoint load failure"

    store = PersistentStore(db_path=str(tmp_path / "store.sqlite3"))
    runner = PipelineRunner(retrieval_adapter=adapter, store=store)

    ctx_human = RoutingContext(ticket_customer_id="cust_1")
    pred_human = IntentPrediction(intent="human_agent", confidence=0.90, model_version="v2.0.0")
    runner.intent_client.classify_intent = lambda text, request_id=None: pred_human
    res_human = runner.run("I need human", ctx_human)
    assert res_human["action"] == "escalate"

    pred_policy = IntentPrediction(intent="return_policy", confidence=0.90, margin=0.5, model_version="v2.0.0")
    runner.intent_client.classify_intent = lambda text, request_id=None: pred_policy
    res_policy = runner.run("What is return policy?", ctx_human)
    assert res_policy["action"] == "escalate"
    assert "insufficient_evidence" in res_policy["reason_codes"]
