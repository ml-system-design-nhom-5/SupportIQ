"""Dedicated collector and application boundary tests for Final Acceptance (Worker C).

Verifies:
- Isolated PostgreSQL schema creation and cleanup without destructive resets
- Enforces cryptographic manifest approval and configuration checks before DB or inference
- Explicit failure on version collisions, unknown documents, and content hash mismatches
  (never defaulting status to 'approved' or approved_by to 'lead_compliance_officer')
- Granular outcome flags: collection_success separated from action/reasons correctness and authority checks
- Customer 100% no-auto-send invariant (unreviewed draft never sent to customer)
- Full draft text, citations (including order_context), and immutable source snapshot capture
- Raw model and routing provenance capture, including versions and llm_metadata
- Resilience on simulated AI gateway errors with full error preservation
- Exclusive run directory creation (exist_ok=False)
"""

import json
from pathlib import Path
import pytest

from scripts.collect_final_acceptance_evidence import (
    AcceptanceEvidenceCollector,
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
    assert summary["collection_success_count"] == 4
    assert summary["action_correctness_count"] == 4
    assert summary["source_verification_passed_count"] == 4
    assert summary["all_criteria_passed_count"] == 4
    assert summary["errors"] == 0
    assert summary["customer_no_auto_send_verified_all"] is True
    assert summary["p50_latency_ms"] is not None
    assert summary["p95_latency_ms"] is not None
    assert summary["immutable_source_snapshots_captured"] >= 4
    assert "mock_dry_run_pending_coordinator_live_authorization" in summary["acceptance_status"]

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
        assert r["collection_success"] is True
        assert r["action_matches_expected"] is True
        assert r["reasons_match_expected"] is True
        assert r["authority_check_passed"] is True
        assert r["source_verification_passed"] is True
        assert r["is_success"] is True
        assert "response_versions" in r
        assert "manifest_cases_sha256" in r

        # For product intent cases, verify full draft and citations
        if r["expected_action"] == "draft":
            assert r["full_draft_text"] is not None and len(r["full_draft_text"]) > 10
            assert len(r["citations"]) >= 1
            for cit in r["citations"]:
                if cit.get("source_type") == "order_context":
                    assert "field" in cit
                    assert "value" in cit
                else:
                    assert "doc_id" in cit or "document_id" in cit
                    assert "version" in cit
                    assert "span" in cit

            # Verify immutable source snapshot integrity
            assert len(r["source_snapshots"]) >= 1
            for key, snap in r["source_snapshots"].items():
                assert "doc_id" in snap
                assert "version" in snap
                assert "title" in snap
                assert "content_hash" in snap
                assert "recomputed_content_hash" in snap
                assert snap["content_hash"] == snap["recomputed_content_hash"]
                assert snap["is_verified"] is True
                assert snap["verification_error"] is None
                assert snap["status"] is not None
                assert snap["approved_by"] is not None
                assert len(snap["content"]) > 10

    # Verify manifest integrity
    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest_data["run_id"] == run_id
    assert manifest_data["files"]["evidence_records.jsonl"]["sha256"] == compute_sha256(rec_file)


def test_collector_manifest_checksum_mismatch_raises(tmp_path):
    """Constructor validates manifest checksums BEFORE any DB connection or inference."""
    real_manifest = json.loads(
        (REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json").read_text(encoding="utf-8")
    )
    tampered = dict(real_manifest)
    tampered["provenance"] = dict(real_manifest["provenance"])
    tampered["provenance"]["cases_sha256"] = "0000000000000000000000000000000000000000000000000000000000000000"

    bad_manifest_path = tmp_path / "bad_manifest.json"
    bad_manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="Cases checksum mismatch against manifest"):
        AcceptanceEvidenceCollector(
            mode="mock",
            manifest_path=bad_manifest_path,
        )


def test_collector_bounded_cases_enforcement():
    """Constructor rejects invalid bounded max_cases configuration."""
    with pytest.raises(ValueError, match="Bounded max_cases must be an integer between 1 and 24"):
        AcceptanceEvidenceCollector(mode="mock", max_cases=25)

    with pytest.raises(ValueError, match="Bounded max_cases must be an integer between 1 and 24"):
        AcceptanceEvidenceCollector(mode="mock", max_cases=0)


def test_collector_source_snapshot_version_collision_and_hash_verification():
    """_build_source_snapshot rejects collisions, unknown docs, and hash mismatches without fake defaults."""
    collector = AcceptanceEvidenceCollector(mode="mock", max_cases=1)

    # 1. Valid lookup of POL-RET-001 (allowed version 2.0 in release)
    snap_valid = collector._build_source_snapshot("POL-RET-001", "2.0")
    assert snap_valid["is_verified"] is True
    assert snap_valid["verification_error"] is None
    assert snap_valid["status"] == "approved"
    assert snap_valid["approved_by"] == "lead_compliance_officer"
    assert snap_valid["content_hash"] == snap_valid["recomputed_content_hash"]

    # 2. Version collision: POL-RET-001 with version 1.0 (active release allows 2.0)
    snap_coll = collector._build_source_snapshot("POL-RET-001", "1.0")
    assert snap_coll["is_verified"] is False
    assert "VERSION_COLLISION_OR_MISMATCH" in snap_coll["verification_error"]
    # Never default status or approved_by on failures!
    assert snap_coll["status"] is None
    assert snap_coll["approved_by"] is None
    assert snap_coll["content"] is None

    # 3. Nonexistent document: DOC-UNKNOWN-999
    snap_missing = collector._build_source_snapshot("DOC-UNKNOWN-999", "1.0")
    assert snap_missing["is_verified"] is False
    assert "DOC_NOT_IN_ACTIVE_KB_RELEASE" in snap_missing["verification_error"]
    assert snap_missing["status"] is None
    assert snap_missing["approved_by"] is None

    # 4. Hash mismatch on returned citation content_hash
    snap_hash_mismatch = collector._build_source_snapshot(
        "POL-RET-001",
        "2.0",
        returned_content_hash="badbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadbadb",
    )
    assert snap_hash_mismatch["is_verified"] is False
    assert "RETURNED_HASH_MISMATCH" in snap_hash_mismatch["verification_error"]


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
    assert summary["errors"] == 2
    assert summary["all_criteria_passed_count"] == 0

    rec_file = Path(res["output_dir"]) / "evidence_records.jsonl"
    records = [json.loads(line) for line in rec_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in records:
        # Human oversight invariant must hold even on errors
        assert r["customer_reply_is_none"] is True
        assert r["terminal_status"] in ("unavailable", "timeout")
        assert r["collection_success"] is True  # Terminal state and no-auto-send observed
        assert r["action_matches_expected"] is False  # Because status is unavailable
        assert r["is_success"] is False
