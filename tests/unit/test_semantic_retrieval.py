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


def test_conflict_detection_handles_universal_condition_all():
    """P2: Handles condition='all' without AttributeError and detects conflicts."""
    rules = [
        {"key": "return_window", "value": 30, "condition": "all"},
        {"key": "return_window", "value": 14, "condition": {"seller": "X"}},
    ]
    # 'all' overlaps with specific condition {'seller': 'X'}, different values -> conflict!
    assert detect_rule_conflicts(rules) is True

    # Same condition, same value -> no conflict
    no_conflict_rules = [
        {"key": "return_window", "value": 30, "condition": "all"},
        {"key": "return_window", "value": 30, "condition": {"seller": "X"}},
    ]
    assert detect_rule_conflicts(no_conflict_rules) is False


def test_adapter_fails_closed_and_quarantines_unapproved_documents(tmp_path):
    """P1: Documents missing approved_by or valid_from are quarantined by adapter and not served."""
    bad_kb_file = tmp_path / "bad_kb.json"
    import json
    bad_kb_file.write_text(json.dumps([
        {
            "document_id": "DOC-UNAPPROVED",
            "status": "approved",
            "allowed_roles": ["agent"],
            # missing approved_by, approved_at, valid_from
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


def test_orchestration_boundary_handles_encoder_failure_gracefully(tmp_path):
    """P1: When encoder fails to load, RetrievalAdapter sets encoder=None and returns encoder_unavailable
    allowing PipelineRunner to execute manual_fallback without crashing initialization.
    """
    from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
    from apps.core_backend.orchestration.store import PersistentStore
    from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction

    # Create an adapter where encoder failed
    adapter = RetrievalAdapter()
    adapter.encoder = None
    adapter.encoder_error = "Mocked checkpoint load failure"

    store = PersistentStore(db_path=str(tmp_path / "store.sqlite3"))
    runner = PipelineRunner(retrieval_adapter=adapter, store=store)

    # Runner initializes successfully despite encoder failure!
    # A human_agent query escalates directly without touching retrieval
    ctx_human = RoutingContext(ticket_customer_id="cust_1")
    pred_human = IntentPrediction(intent="human_agent", confidence=0.90, model_version="v2.0.0")
    runner.intent_client.classify_intent = lambda text, request_id=None: pred_human
    res_human = runner.run("I need human", ctx_human)
    assert res_human["action"] == "escalate"

    # A policy query requiring retrieval escalates due to insufficient evidence rather than crashing
    pred_policy = IntentPrediction(intent="return_policy", confidence=0.90, margin=0.5, model_version="v2.0.0")
    runner.intent_client.classify_intent = lambda text, request_id=None: pred_policy
    res_policy = runner.run("What is return policy?", ctx_human)
    assert res_policy["action"] == "escalate"
    assert "insufficient_evidence" in res_policy["reason_codes"]
