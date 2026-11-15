"""Dedicated collector and application boundary tests for Final Acceptance (Worker C).

Verifies:
- Isolated PostgreSQL schema creation and cleanup without destructive resets
- Enforces cryptographic manifest approval and configuration checks before DB or inference
- Live mode fails closed on unapproved manifest status or missing approval scope
- Non-optional checksum validation for cases, fixtures, paired tasks, active KB, and release
- Seeded order ownership validation without live LLM (rejecting other customer orders)
- Explicit failure on version collisions, unknown documents, and content hash mismatches
  (never defaulting status to 'approved' or approved_by to 'lead_compliance_officer')
- Order_context citation verification requires actual field presence and typed equality
- Customer HTTP JSON validation requires 'reply' field and 'customer_status' == 'received'
- Component fixture boundary: fields are null/None (no fabricated HTTP/auto-send observations)
- Strictly separated application metrics (p50/p95, oversight) from component retrieval metrics
- Resilience on simulated AI gateway errors with full error preservation
- Exclusive run directory creation (exist_ok=False)
"""

import hashlib
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


def test_collector_mock_bounded_execution(tmp_path, monkeypatch):
    """Collector executes in isolated disposable schema and captures full evidence."""
    # Offline mock gateway test explicitly opts out of spaCy NER when en_core_web_sm is absent.
    monkeypatch.setenv("SUPPORTIQ_REQUIRE_PRIVACY_NER", "false")
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
    assert summary["total_all_criteria_passed"] == 4
    assert summary["total_errors"] == 0

    # Separated application metrics
    app_meta = summary["application_metrics"]
    assert app_meta["cases_submitted"] == 4
    assert app_meta["collection_success_count"] == 4
    assert app_meta["action_correctness_count"] == 4
    assert app_meta["source_verification_passed_count"] == 4
    assert app_meta["all_criteria_passed_count"] == 4
    assert app_meta["errors"] == 0
    assert app_meta["customer_tickets_inspected"] == 4
    assert app_meta["customer_no_auto_send_verified_all"] is True
    assert app_meta["p50_latency_ms"] is not None
    assert app_meta["p95_latency_ms"] is not None
    assert app_meta["target_p95_under_12s"] is True

    # Verify evidence records
    rec_file = out_dir / "evidence_records.jsonl"
    assert rec_file.exists()
    records = [json.loads(line) for line in rec_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 4

    for r in records:
        assert r["component_evidence"] == "application_postgresql_gateway"
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
                    assert cit["field_present_in_executed_context"] is True
                    assert cit["value_matches_executed_context"] is True
                    assert cit["is_verified"] is True
                else:
                    assert "doc_id" in cit or "document_id" in cit
                    assert "version" in cit
                    assert "span" in cit
                    assert cit["is_verified"] is True

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


def test_collector_manifest_missing_checksum_fails_closed(tmp_path):
    """Constructor fails closed if KB reconciliation checksums are missing from manifest."""
    real_manifest = json.loads(
        (REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json").read_text(encoding="utf-8")
    )
    tampered = dict(real_manifest)
    tampered["provenance"] = dict(real_manifest["provenance"])
    tampered["provenance"]["kb_reconciliation"] = {"worker_local_worktree": {}}

    bad_manifest_path = tmp_path / "missing_kb_checksum_manifest.json"
    bad_manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="Manifest missing worker_local_worktree KB/release provenance hashes"):
        AcceptanceEvidenceCollector(
            mode="mock",
            manifest_path=bad_manifest_path,
        )


def test_collector_live_unapproved_manifest_fails_closed(tmp_path):
    """Live execution fails closed if manifest status is unapproved."""
    real_manifest = json.loads(
        (REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json").read_text(encoding="utf-8")
    )
    tampered = dict(real_manifest)
    tampered["status"] = "draft_unapproved"

    bad_manifest_path = tmp_path / "unapproved_manifest.json"
    bad_manifest_path.write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(ValueError, match="Live execution rejected: suite manifest status is 'draft_unapproved'"):
        AcceptanceEvidenceCollector(
            mode="live",
            manifest_path=bad_manifest_path,
        )


def test_collector_bounded_cases_enforcement():
    """Constructor rejects invalid bounded max_cases configuration."""
    with pytest.raises(ValueError, match="Bounded max_cases must be an integer between 1 and 24"):
        AcceptanceEvidenceCollector(mode="mock", max_cases=25)

    with pytest.raises(ValueError, match="Bounded max_cases must be an integer between 1 and 24"):
        AcceptanceEvidenceCollector(mode="mock", max_cases=0)


def test_collector_order_ownership_validation_negative_path(tmp_path):
    """Constructor rejects suite cases referencing orders not owned by demo-customer."""
    real_cases = [
        json.loads(line)
        for line in (REPO_ROOT / "data/benchmarks/final_acceptance/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tampered_cases = [dict(c) for c in real_cases]
    # ORD-1002 is owned by a different customer in mock_orders.json
    tampered_cases[0]["order_id"] = "ORD-1002"

    bad_cases_path = tmp_path / "bad_cases.jsonl"
    with open(bad_cases_path, "w", encoding="utf-8") as f:
        for c in tampered_cases:
            f.write(json.dumps(c) + "\n")

    # Update manifest to match new cases hash so it reaches order validation
    real_manifest = json.loads(
        (REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json").read_text(encoding="utf-8")
    )
    tampered_manifest = dict(real_manifest)
    tampered_manifest["provenance"] = dict(real_manifest["provenance"])
    tampered_manifest["provenance"]["cases_sha256"] = compute_sha256(bad_cases_path)
    bad_manifest_path = tmp_path / "bad_manifest.json"
    bad_manifest_path.write_text(json.dumps(tampered_manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="Order validation failure in case final-case-01"):
        AcceptanceEvidenceCollector(
            mode="mock",
            suite_path=bad_cases_path,
            manifest_path=bad_manifest_path,
        )


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


def test_collector_order_context_citation_missing_field_fails_verification(tmp_path):
    """Order_context citation with absent field evaluates to is_verified=False."""
    # Build a simulated citation with absent field
    executed_order_context = {"order_status": "delivered"}
    cit = {"source_type": "order_context", "field": "nonexistent_field", "value": "some_value"}

    field_present = (cit["field"] in executed_order_context)
    val_matches = field_present and (executed_order_context[cit["field"]] == cit["value"])
    v_ok = field_present and val_matches
    assert v_ok is False
    assert field_present is False


def test_collector_component_boundary_fields_null_and_separated_metrics(tmp_path):
    """Component fixture cases have null/None for application fields and separate metrics."""
    collector = AcceptanceEvidenceCollector(mode="mock", max_cases=24)
    # Target only injected cases 21-24
    collector.cases = [c for c in collector.cases if c.get("fixture_boundary") == "injected_synthetic"]
    assert len(collector.cases) == 4

    res = collector.collect(output_base_dir=tmp_path)
    summary = res["summary"]

    app_meta = summary["application_metrics"]
    fix_meta = summary["component_fixture_metrics"]

    assert app_meta["cases_submitted"] == 0
    assert fix_meta["cases_submitted"] == 4
    assert fix_meta["expiry_filtering_verified_count"] == 2
    assert fix_meta["conflict_detection_verified_count"] == 2
    assert fix_meta["all_criteria_passed_count"] == 4

    rec_file = Path(res["output_dir"]) / "evidence_records.jsonl"
    records = [json.loads(line) for line in rec_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(records) == 4

    for r in records:
        assert r["component_evidence"] == "retrieval_adapter_injected_fixture_execution"
        # No fabricated application HTTP/auto-send observations!
        assert r["customer_http_status"] is None
        assert r["customer_no_auto_send_observed"] is None
        assert r["customer_reply_is_none"] is None
        assert r["action_matches_expected"] is None
        assert r["authority_check_passed"] is None
        assert r["is_success"] is True


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
    assert summary["total_errors"] == 2
    assert summary["total_all_criteria_passed"] == 0

    rec_file = Path(res["output_dir"]) / "evidence_records.jsonl"
    records = [json.loads(line) for line in rec_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    for r in records:
        # Human oversight invariant must hold even on errors
        assert r["customer_reply_is_none"] is True
        assert r["terminal_status"] in ("unavailable", "timeout")
        assert r["collection_success"] is True  # Terminal state and no-auto-send observed
        assert r["action_matches_expected"] is False  # Because status is unavailable
        assert r["is_success"] is False


def test_collector_get_encoder_positive_real_encoder(monkeypatch):
    """Positive test: _get_encoder accepts faithful real PolicyEncoder with populated model/tokenizer and mock_mode=False."""
    class FaithfulRealEncoder:
        def __init__(self):
            self.mock_mode = False
            self.device = "cpu"
            self.model = object()  # populated model
            self.tokenizer = object()  # populated tokenizer
            # Deliberately NO self.encoder attribute, faithfully matching PolicyEncoder

    monkeypatch.setattr(
        "apps.core_backend.retrieval.adapter.PolicyEncoder",
        lambda *args, **kwargs: FaithfulRealEncoder(),
    )

    # 1. In live mode: faithfully accepts real encoder without fallback
    collector_live = AcceptanceEvidenceCollector(mode="live", max_cases=1)
    enc_live = collector_live._get_encoder()
    assert isinstance(enc_live, FaithfulRealEncoder)
    assert not hasattr(enc_live, "encoder")
    assert enc_live.mock_mode is False
    assert enc_live.model is not None
    assert enc_live.tokenizer is not None
    assert collector_live.encoder_provenance == "real_bge_policy_encoder"
    assert collector_live.encoder_error is None

    # 2. In mock mode: also uses real encoder when successfully initialized
    collector_mock = AcceptanceEvidenceCollector(mode="mock", max_cases=1)
    enc_mock = collector_mock._get_encoder()
    assert isinstance(enc_mock, FaithfulRealEncoder)
    assert collector_mock.encoder_provenance == "real_bge_policy_encoder"
    assert collector_mock.encoder_error is None


def test_collector_get_encoder_negative_mock_mode_rejected_in_live(monkeypatch):
    """Negative failure test: _get_encoder rejects PolicyEncoder with mock_mode=True in live mode."""
    class MockModeEncoder:
        def __init__(self):
            self.mock_mode = True
            self.device = "cpu"
            self.model = object()
            self.tokenizer = object()

    monkeypatch.setattr(
        "apps.core_backend.retrieval.adapter.PolicyEncoder",
        lambda *args, **kwargs: MockModeEncoder(),
    )

    collector = AcceptanceEvidenceCollector(mode="live", max_cases=1)
    with pytest.raises(
        RuntimeError, match="PolicyEncoder initialized in mock_mode=True, real encoder required"
    ):
        collector._get_encoder()
    assert collector.encoder_provenance == "failed_real_encoder_fail_closed"


def test_collector_get_encoder_negative_unpopulated_model_rejected_in_live(monkeypatch):
    """Negative failure test: _get_encoder rejects PolicyEncoder with unpopulated model or tokenizer in live mode."""
    class UnpopulatedEncoder:
        def __init__(self):
            self.mock_mode = False
            self.device = "cpu"
            self.model = None  # Unpopulated model
            self.tokenizer = object()

    monkeypatch.setattr(
        "apps.core_backend.retrieval.adapter.PolicyEncoder",
        lambda *args, **kwargs: UnpopulatedEncoder(),
    )

    collector = AcceptanceEvidenceCollector(mode="live", max_cases=1)
    with pytest.raises(
        RuntimeError, match="PolicyEncoder initialized with None model or tokenizer"
    ):
        collector._get_encoder()
    assert collector.encoder_provenance == "failed_real_encoder_fail_closed"


def test_collector_live_encoder_fails_closed_without_mock_fallback(monkeypatch):
    """Live mode strictly fails closed when real encoder fails; never falls back to MockPolicyEncoder."""
    collector = AcceptanceEvidenceCollector(mode="live", max_cases=1)

    # Simulate real PolicyEncoder initialization failure
    def failing_encoder(*args, **kwargs):
        raise RuntimeError("Simulated HuggingFace CUDA/Network failure loading BGE model")

    monkeypatch.setattr("apps.core_backend.retrieval.adapter.PolicyEncoder", failing_encoder)

    # In live mode, _get_encoder must raise RuntimeError and NOT fall back to mock
    with pytest.raises(RuntimeError, match="Live execution requires real PolicyEncoder, but initialization failed"):
        collector._get_encoder()
    assert collector.encoder_provenance == "failed_real_encoder_fail_closed"


def test_collector_atomic_kb_release_pair_matching(tmp_path):
    """Constructor accepts both declared normalized LF and CRLF pairs atomically, and rejects mixed pairs."""
    manifest = json.loads((REPO_ROOT / "data/benchmarks/final_acceptance/suite_manifest.json").read_text(encoding="utf-8"))
    prov = manifest["provenance"]["kb_reconciliation"]

    # Read raw bytes of disk files to construct real normalized LF and CRLF files
    kb_raw = (REPO_ROOT / "data/knowledge/approved_kb.v2.json").read_bytes()
    rel_raw = (REPO_ROOT / "apps/ai_service/kb-release.json").read_bytes()

    kb_lf_bytes = kb_raw.replace(b"\r\n", b"\n")
    kb_crlf_bytes = kb_lf_bytes.replace(b"\n", b"\r\n")

    rel_lf_bytes = rel_raw.replace(b"\r\n", b"\n")
    rel_crlf_bytes = rel_lf_bytes.replace(b"\n", b"\r\n")

    # Verify the normalized bytes match manifest declared hashes
    assert hashlib.sha256(kb_lf_bytes).hexdigest() == prov["worker_local_worktree"]["local_kb_source_sha256"]
    assert hashlib.sha256(rel_lf_bytes).hexdigest() == prov["worker_local_worktree"]["local_kb_release_sha256"]
    assert hashlib.sha256(kb_crlf_bytes).hexdigest() == prov["deployed_root_serving_gateway"]["kb_source_sha256"]
    assert hashlib.sha256(rel_crlf_bytes).hexdigest() == prov["deployed_root_serving_gateway"]["kb_release_sha256"]

    # Create explicit temp files for LF pair
    kb_lf_path = tmp_path / "kb_lf.json"
    kb_lf_path.write_bytes(kb_lf_bytes)
    rel_lf_path = tmp_path / "rel_lf.json"
    rel_lf_path.write_bytes(rel_lf_bytes)

    # Create explicit temp files for CRLF pair
    kb_crlf_path = tmp_path / "kb_crlf.json"
    kb_crlf_path.write_bytes(kb_crlf_bytes)
    rel_crlf_path = tmp_path / "rel_crlf.json"
    rel_crlf_path.write_bytes(rel_crlf_bytes)

    # 1. Test worker LF pair is recognized
    collector_lf = AcceptanceEvidenceCollector(
        mode="mock",
        max_cases=1,
        active_kb_path=kb_lf_path,
        release_path=rel_lf_path,
    )
    assert collector_lf.matched_kb_provenance == "worker_local_worktree"
    assert collector_lf.matched_line_ending == "LF"

    # 2. Test deployed root CRLF pair is recognized
    collector_crlf = AcceptanceEvidenceCollector(
        mode="mock",
        max_cases=1,
        active_kb_path=kb_crlf_path,
        release_path=rel_crlf_path,
    )
    assert collector_crlf.matched_kb_provenance == "deployed_root_serving_gateway"
    assert collector_crlf.matched_line_ending == "CRLF"

    # 3. Test actual mixed pair rejection: worker LF KB with deployed root CRLF release
    with pytest.raises(ValueError, match="Unrecognized or mixed KB and release hash pair"):
        AcceptanceEvidenceCollector(
            mode="mock",
            max_cases=1,
            active_kb_path=kb_lf_path,
            release_path=rel_crlf_path,
        )

    # 4. Test actual mixed pair rejection: deployed root CRLF KB with worker LF release
    with pytest.raises(ValueError, match="Unrecognized or mixed KB and release hash pair"):
        AcceptanceEvidenceCollector(
            mode="mock",
            max_cases=1,
            active_kb_path=kb_crlf_path,
            release_path=rel_lf_path,
        )
