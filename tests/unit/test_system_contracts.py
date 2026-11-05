import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    load_system_inputs,
    verify_input_snapshot,
    SystemCase,
    SystemConfig,
    CaseResult,
    VerifiedSystemInputs,
)
from pipeline.preparation.utils import compute_sha256

REPO_ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def minimal_benchmark_env(tmp_path):
    """Create a minimal valid benchmark environment with manifest, cases, config, and KB."""
    bench_dir = tmp_path / "benchmarks" / "system" / "v1"
    bench_dir.mkdir(parents=True)
    kb_path = tmp_path / "kb.json"
    
    # Valid KB document
    kb_data = [{
        "doc_id": "KB-RET-001",
        "title": "Standard Return Policy",
        "version": "1.0",
        "status": "approved",
        "allowed_roles": ["agent", "customer"],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2027-01-01T00:00:00Z",
        "approved_by": "lead_reviewer",
        "approved_at": "2026-01-01T00:00:00Z",
        "content": "Return items within 30 days."
    }]
    kb_path.write_text(json.dumps(kb_data), encoding="utf-8")
    kb_hash = compute_sha256(kb_path)

    cases_path = bench_dir / "cases.jsonl"
    case_1 = {
        "id": "case-001",
        "primary_slice": "supported",
        "tags": ["policy", "answerable"],
        "text": "What is the return policy?",
        "true_intent": "return_policy",
        "context": {
            "ticket_customer_id": "demo-customer",
            "verified_scope": "ticket:read",
            "is_personal_lookup": False
        },
        "expected": {
            "actions": ["retrieve_draft"],
            "team": "returns_support",
            "reason_any": [],
            "must_escalate": False,
            "must_not_draft": False,
            "retrieval_applicable": True,
            "answerable": True,
            "gold_sources": [{"doc_id": "KB-RET-001", "version": "1.0"}],
            "draft_expected": True
        },
        "fault": None
    }
    cases_path.write_text(json.dumps(case_1) + "\n", encoding="utf-8")
    cases_hash = compute_sha256(cases_path)

    manifest_path = bench_dir / "suite_manifest.json"
    manifest = {
        "schema_version": "v1.0",
        "suite_id": "sys-bench-v1",
        "split": "acceptance",
        "status": "approved",
        "reviewed_by": "qa_lead",
        "reviewed_at": "2026-11-04T00:00:00Z",
        "as_of": "2026-11-05T00:00:00Z",
        "files": {
            "cases": {"path": "cases.jsonl", "sha256": cases_hash},
            "kb": {"path": str(kb_path.relative_to(tmp_path)), "sha256": kb_hash}
        }
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    config_path = tmp_path / "system_evaluation.json"
    config = {
        "schema_version": "v1.0",
        "seed": 42,
        "concurrency": 1,
        "warmup_requests": 5,
        "latency_requests": 100,
        "max_llm_calls": 200,
        "deadline_seconds": 30.0,
        "ml_timeout_seconds": 3.0,
        "llm_timeout_seconds": 15.0,
        "demo_timeout_seconds": 20.0,
        "max_estimated_cost_usd": 1.0,
        "mandatory_gates": ["routing_guardrails", "retrieval_safety"],
        "thresholds": {"recall_at_3": 0.80, "grounded_claims": 0.90}
    }
    config_path.write_text(json.dumps(config), encoding="utf-8")

    return {
        "root": tmp_path,
        "manifest_path": manifest_path,
        "cases_path": cases_path,
        "config_path": config_path,
        "kb_path": kb_path,
        "case_1": case_1,
        "manifest": manifest,
        "kb_data": kb_data
    }


def test_valid_benchmark_loads_properly(minimal_benchmark_env):
    env = minimal_benchmark_env
    inputs = load_system_inputs(
        repo_root=env["root"],
        suite_path=env["manifest_path"],
        config_path=env["config_path"],
        profile="mock"
    )
    assert isinstance(inputs, VerifiedSystemInputs)
    assert len(inputs.cases) == 1
    assert inputs.cases[0].id == "case-001"
    assert inputs.cases[0].true_intent == "return_policy"
    assert inputs.config.seed == 42


def test_duplicate_case_ids_rejected(minimal_benchmark_env):
    env = minimal_benchmark_env
    c1 = env["case_1"]
    c2 = dict(c1)  # duplicate ID
    env["cases_path"].write_text(json.dumps(c1) + "\n" + json.dumps(c2) + "\n", encoding="utf-8")
    
    # Update hash in manifest
    env["manifest"]["files"]["cases"]["sha256"] = compute_sha256(env["cases_path"])
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    with pytest.raises(EvaluationError, match="duplicate.*case"):
        load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")


def test_invalid_intent_rejected(minimal_benchmark_env):
    env = minimal_benchmark_env
    c1 = dict(env["case_1"])
    c1["true_intent"] = "non_existent_fake_intent"
    env["cases_path"].write_text(json.dumps(c1) + "\n", encoding="utf-8")
    
    env["manifest"]["files"]["cases"]["sha256"] = compute_sha256(env["cases_path"])
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    with pytest.raises(EvaluationError, match="outside expected taxonomy"):
        load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")


def test_ood_null_intent_accepted(minimal_benchmark_env):
    env = minimal_benchmark_env
    c1 = dict(env["case_1"])
    c1["expected"] = dict(env["case_1"]["expected"])
    c1["true_intent"] = None  # Valid OOD
    c1["tags"] = ["ood", "uncertainty"]
    c1["expected"]["actions"] = ["escalate"]
    c1["expected"]["answerable"] = False
    c1["expected"]["gold_sources"] = []
    c1["expected"]["must_escalate"] = True
    c1["expected"]["draft_expected"] = False
    env["cases_path"].write_text(json.dumps(c1) + "\n", encoding="utf-8")
    
    env["manifest"]["files"]["cases"]["sha256"] = compute_sha256(env["cases_path"])
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    inputs = load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")
    assert inputs.cases[0].true_intent is None


def test_missing_or_mismatched_checksum_rejected(minimal_benchmark_env):
    env = minimal_benchmark_env
    env["manifest"]["files"]["cases"]["sha256"] = "wrong_sha256_hash"
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    with pytest.raises(EvaluationError, match="checksum mismatch"):
        load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")


def test_path_escape_rejected(minimal_benchmark_env):
    env = minimal_benchmark_env
    env["manifest"]["files"]["cases"]["path"] = "../../../../escaped.txt"
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    with pytest.raises(EvaluationError, match="escapes repo root"):
        load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")


def test_expired_gold_document_rejected(minimal_benchmark_env):
    env = minimal_benchmark_env
    # Make KB document expired before as_of date
    env["kb_data"][0]["valid_to"] = "2026-06-01T00:00:00Z"
    env["kb_path"].write_text(json.dumps(env["kb_data"]), encoding="utf-8")
    env["manifest"]["files"]["kb"]["sha256"] = compute_sha256(env["kb_path"])
    # as_of is 2026-11-05T00:00:00Z > valid_to
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    with pytest.raises(EvaluationError, match="expired or ineligible"):
        load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")


def test_draft_suite_cannot_be_acceptance_ready(minimal_benchmark_env):
    env = minimal_benchmark_env
    env["manifest"]["status"] = "draft"
    env["manifest_path"].write_text(json.dumps(env["manifest"]), encoding="utf-8")

    # In mock mode, draft is allowed with warning/flag
    inputs_mock = load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")
    assert inputs_mock.manifest["status"] == "draft"

    # In live acceptance mode, draft status MUST be rejected
    with pytest.raises(EvaluationError, match="Suite in 'draft' status cannot be used for live acceptance"):
        load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="live")


def test_verify_input_snapshot_detects_mutation(minimal_benchmark_env):
    env = minimal_benchmark_env
    inputs = load_system_inputs(env["root"], env["manifest_path"], env["config_path"], profile="mock")
    
    # Snapshot clean
    verify_input_snapshot(inputs)

    # Tamper with cases file
    env["cases_path"].write_text(env["cases_path"].read_text() + "\n# Tampered", encoding="utf-8")

    # Verification must detect mutation mid-run
    with pytest.raises(EvaluationError, match="Input file modified mid-run"):
        verify_input_snapshot(inputs)


def test_official_156_cases_benchmark_suite_loads_and_verifies():
    suite_path = REPO_ROOT / "data" / "benchmarks" / "system" / "v1" / "suite_manifest.json"
    config_path = REPO_ROOT / "pipeline" / "configs" / "system_evaluation.json"
    inputs = load_system_inputs(
        repo_root=REPO_ROOT,
        suite_path=suite_path,
        config_path=config_path,
        profile="mock"
    )
    assert len(inputs.cases) == 156
    assert inputs.coverage["slice_counts"]["supported"] == 60
    assert inputs.coverage["slice_counts"]["unsupported"] == 34
    assert inputs.coverage["slice_counts"]["answerable"] == 24
    assert inputs.coverage["slice_counts"]["unanswerable"] == 18
    assert inputs.coverage["slice_counts"]["uncertainty_and_faults"] == 20

    # Also test fixture suite
    fix_suite = REPO_ROOT / "tests" / "fixtures" / "system_evaluation" / "suite_manifest.json"
    fix_config = REPO_ROOT / "tests" / "fixtures" / "system_evaluation" / "config.json"
    fix_inputs = load_system_inputs(
        repo_root=REPO_ROOT,
        suite_path=fix_suite,
        config_path=fix_config,
        profile="mock"
    )
    assert len(fix_inputs.cases) == 5

