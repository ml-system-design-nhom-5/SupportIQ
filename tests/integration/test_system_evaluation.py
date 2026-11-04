"""Integration tests for System Evaluation CLI, end-to-end mock execution, and atomic publishing."""

import json
import pytest
from pathlib import Path
from datetime import datetime, timezone

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.run_system_evaluation import run_system_evaluation
from pipeline.evaluation.run_evaluation import main as cli_main
from pipeline.preparation.utils import compute_sha256

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def minimal_system_suite(tmp_path):
    bench_dir = tmp_path / "benchmarks" / "system" / "v1"
    bench_dir.mkdir(parents=True)

    kb_data = [{
        "doc_id": "KB-1",
        "title": "Return Policy",
        "version": "1.0",
        "status": "approved",
        "allowed_roles": ["agent", "customer"],
        "valid_from": "2026-01-01T00:00:00Z",
        "valid_to": "2027-01-01T00:00:00Z",
        "approved_by": "lead",
        "approved_at": "2026-01-01T00:00:00Z",
        "content": "Return items within 30 days.",
    }]
    kb_path = bench_dir / "kb.json"
    kb_path.write_text(json.dumps(kb_data), encoding="utf-8")

    cases_path = bench_dir / "cases.jsonl"
    case = {
        "id": "c-01",
        "primary_slice": "supported",
        "tags": ["policy"],
        "text": "What is the return window?",
        "true_intent": "return_policy",
        "context": {"ticket_customer_id": "cust-1"},
        "expected": {
            "actions": ["retrieve_draft"],
            "must_escalate": False,
            "answerable": True,
            "gold_sources": [{"doc_id": "KB-1", "version": "1.0"}],
            "draft_expected": True,
        },
    }
    cases_path.write_text(json.dumps(case) + "\n", encoding="utf-8")

    manifest = {
        "schema_version": "v1.0",
        "suite_id": "sys-test-suite",
        "split": "acceptance",
        "status": "approved",
        "as_of": "2026-11-05T00:00:00Z",
        "files": {
            "cases": {"path": "cases.jsonl", "sha256": compute_sha256(cases_path)},
            "kb": {"path": "kb.json", "sha256": compute_sha256(kb_path)},
        },
    }
    manifest_path = bench_dir / "suite_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    config = {
        "schema_version": "v1.0",
        "max_llm_calls": 20,
        "deadline_seconds": 5.0,
        "warmup_requests": 1,
        "latency_requests": 2,
        "mandatory_gates": ["routing_guardrails", "retrieval_safety"],
    }
    config_path = tmp_path / "system_evaluation.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    return {
        "suite_path": manifest_path,
        "config_path": config_path,
        "root": tmp_path,
    }


def test_run_system_evaluation_mock_creates_all_artifacts(minimal_system_suite, tmp_path):
    """run_system_evaluation under mock profile executes offline and generates all artifacts."""
    out_root = tmp_path / "artifacts" / "evaluation"

    run_dir = run_system_evaluation(
        suite_path=minimal_system_suite["suite_path"],
        config_path=minimal_system_suite["config_path"],
        profile="mock",
        run_id="sys-mock-run-001",
        output_root=out_root,
        repo_root=minimal_system_suite["root"],
    )

    assert run_dir.exists()
    expected_files = [
        "config.resolved.json",
        "environment.json",
        "inputs.json",
        "results.jsonl",
        "component_results.jsonl",
        "oversight_results.jsonl",
        "metrics.json",
        "slices.csv",
        "requirements_matrix.csv",
        "latency.json",
        "cost.json",
        "claims_to_annotate.jsonl",
        "product_sessions.template.csv",
        "report.md",
        "run_state.json",
        "manifest.json",
    ]

    for fname in expected_files:
        p = run_dir / fname
        assert p.exists(), f"Missing expected output artifact: {fname}"

    # Verify manifest contains valid SHA-256 checksums
    manifest_file = run_dir / "manifest.json"
    man_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert man_data["status"] == "completed"
    assert man_data["profile"] == "mock"
    for f_key, f_meta in man_data["files"].items():
        actual_sha = compute_sha256(run_dir / f_meta["path"])
        assert actual_sha == f_meta["sha256"]

    # Refuse existing run ID
    with pytest.raises(EvaluationError, match="already exists"):
        run_system_evaluation(
            suite_path=minimal_system_suite["suite_path"],
            config_path=minimal_system_suite["config_path"],
            profile="mock",
            run_id="sys-mock-run-001",
            output_root=out_root,
            repo_root=minimal_system_suite["root"],
        )


def test_cli_mode_system_dispatches_cleanly(minimal_system_suite, tmp_path):
    """CLI --mode system --profile mock returns exit code 2 (since simulated evidence cannot certify acceptance)."""
    out_root = tmp_path / "artifacts_cli" / "evaluation"

    exit_code = cli_main([
        "--mode", "system",
        "--profile", "mock",
        "--suite", str(minimal_system_suite["suite_path"]),
        "--config", str(minimal_system_suite["config_path"]),
        "--run-id", "sys-cli-run-001",
        "--output-root", str(out_root),
    ])
    # Code 2: executed successfully but simulated evidence / insufficient evidence for acceptance
    assert exit_code == 2
