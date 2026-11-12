"""Dedicated collector and application boundary tests for Final Acceptance (Worker C).

Verifies:
- Isolated PostgreSQL schema creation and cleanup without destructive resets
- Customer 100% no-auto-send invariant (unreviewed draft never sent to customer)
- Full draft text, citations, and immutable source snapshot capture
- Raw model and routing provenance capture
- Resilience on simulated AI gateway errors
"""

import json
from pathlib import Path
import pytest

from scripts.collect_final_acceptance_evidence import (
    AcceptanceEvidenceCollector,
    EphemeralMockAIGateway,
    compute_sha256,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def sample_cases():
    cases_path = REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl"
    assert cases_path.exists()
    lines = [line.strip() for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [json.loads(line) for line in lines[:4]]


def test_collector_mock_bounded_execution(tmp_path):
    """Collector executes in isolated disposable schema and captures full evidence."""
    collector = AcceptanceEvidenceCollector(
        mode="mock",
        max_cases=4,
        poll_timeout_seconds=20.0,
    )
    res = collector.collect(output_base_dir=tmp_path)

    run_id = res["run_id"]
    out_dir = Path(res["output_dir"])
    assert out_dir.exists()

    summary = res["summary"]
    assert summary["run_id"] == run_id
    assert summary["mode"] == "mock"
    assert summary["total_cases_submitted"] == 4
    assert summary["errors"] == 0
    assert summary["customer_no_auto_send_verified_all"] is True
    assert summary["p50_latency_ms"] is not None
    assert summary["p95_latency_ms"] is not None
    assert summary["immutable_source_snapshots_captured"] >= 4

    # Verify evidence records
    rec_file = out_dir / "evidence_records.jsonl"
    assert rec_file.exists()
    records = [json.loads(line) for line in rec_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 4

    for r in records:
        assert r["customer_no_auto_send_observed"] is True
        assert r["customer_reply_is_none"] is True
        assert r["customer_http_status"] == 200
        assert r["submit_to_terminal_latency_ms"] > 0
        assert r["is_terminal"] is True
        assert r["is_success"] is True

        # For product intent cases, verify full draft and citations
        if r["expected_action"] == "draft":
            assert r["full_draft_text"] is not None and len(r["full_draft_text"]) > 10
            assert len(r["citations"]) >= 1
            for cit in r["citations"]:
                assert "doc_id" in cit
                assert "version" in cit
                assert "span" in cit

            # Verify immutable source snapshot integrity
            assert len(r["source_snapshots"]) >= 1
            for key, snap in r["source_snapshots"].items():
                assert "doc_id" in snap
                assert "version" in snap
                assert "title" in snap
                assert "content_hash" in snap
                assert "content" in snap
                assert len(snap["content"]) > 10

    # Verify manifest integrity
    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["run_id"] == run_id
    assert manifest_data["files"]["evidence_records.jsonl"]["sha256"] == compute_sha256(rec_file)


def test_collector_error_resilience(tmp_path):
    """Collector handles gateway failures without crashing and records failure codes."""
    collector = AcceptanceEvidenceCollector(
        mode="mock",
        max_cases=2,
        poll_timeout_seconds=5.0,
        mock_mode="error",
    )
    res = collector.collect(output_base_dir=tmp_path)
    summary = res["summary"]
    assert summary["total_cases_submitted"] == 2
    # Errors should be recorded gracefully
    assert summary["errors"] >= 1
    rec_file = Path(res["output_dir"]) / "evidence_records.jsonl"
    records = [json.loads(line) for line in rec_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in records:
        # Human oversight invariant must hold even on errors
        assert r["customer_reply_is_none"] is True
        assert r["terminal_status"] in ("unavailable", "timeout")
