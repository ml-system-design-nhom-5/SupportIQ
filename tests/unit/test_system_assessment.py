"""Unit tests for Human Assessment, claim annotation verification, and product session analysis."""

import json
import pytest
from pathlib import Path

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.assess_system import (
    assess_run,
    evaluate_claim_annotations,
    evaluate_product_sessions,
)
from pipeline.preparation.utils import compute_sha256


@pytest.fixture
def mock_run_dir(tmp_path):
    """Create a minimal completed run directory with manifest and results."""
    run_dir = tmp_path / "system_run_001"
    run_dir.mkdir(parents=True)

    results_file = run_dir / "results.jsonl"
    r1 = {
        "case_id": "c1",
        "repetition": 1,
        "profile": "live",
        "scope": "e2e",
        "execution_status": "ok",
        "error_code": None,
        "routing_action": "retrieve_draft",
        "final_action": "retrieve_draft",
        "requested_team": None,
        "target_queue": None,
        "reason_codes": [],
        "predicted_intent": "return_policy",
        "final_intent": "return_policy",
        "prediction_confidence": 0.95,
        "prediction_margin": 0.5,
        "sources": [{"doc_id": "KB-1", "version": "1.0"}],
        "draft_body": "You have 30 days to return items.",
        "draft_kind": "policy_faq",
        "draft_hash": "sha256-draft-c1-hash",
        "llm_called": True,
        "llm_metadata": None,
        "llm_usage": None,
        "stage_elapsed_ms": {},
        "total_elapsed_ms": 150.0,
        "audit_evidence": None,
    }
    r2 = {
        "case_id": "c2",
        "repetition": 1,
        "profile": "live",
        "scope": "e2e",
        "execution_status": "ok",
        "error_code": None,
        "routing_action": "retrieve_draft",
        "final_action": "retrieve_draft",
        "requested_team": None,
        "target_queue": None,
        "reason_codes": [],
        "predicted_intent": "shipping_policy",
        "final_intent": "shipping_policy",
        "prediction_confidence": 0.92,
        "prediction_margin": 0.4,
        "sources": [{"doc_id": "KB-2", "version": "1.0"}],
        "draft_body": "Shipping takes 3 to 5 business days.",
        "draft_kind": "policy_faq",
        "draft_hash": "sha256-draft-c2-hash",
        "llm_called": True,
        "llm_metadata": None,
        "llm_usage": None,
        "stage_elapsed_ms": {},
        "total_elapsed_ms": 140.0,
        "audit_evidence": None,
    }
    results_content = json.dumps(r1) + "\n" + json.dumps(r2) + "\n"
    results_file.write_text(results_content, encoding="utf-8")
    results_sha = compute_sha256(results_file)

    manifest_file = run_dir / "manifest.json"
    manifest = {
        "schema_version": "v1.0",
        "run_id": "system_run_001",
        "profile": "live",
        "status": "completed",
        "files": {
            "results.jsonl": {"path": "results.jsonl", "sha256": results_sha}
        },
    }
    manifest_file.write_text(json.dumps(manifest), encoding="utf-8")

    return run_dir


class TestClaimAnnotations:
    def test_supported_claims_ratio_threshold_89_fails_90_passes(self):
        """89/100 claims supported fails < 0.90 threshold; 90/100 passes."""
        # 89 supported, 11 unsupported
        ann_89 = [
            {
                "case_id": "c1",
                "draft_sha256": "sha256-draft-c1-hash",
                "reviewer": "eval_lead",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "attestation": {"all_factual_claims_identified": True},
                "claims": (
                    [{"claim_id": f"s_{i}", "verdict": "supported"} for i in range(89)]
                    + [{"claim_id": f"u_{i}", "verdict": "unsupported"} for i in range(11)]
                ),
            }
        ]
        res_89 = evaluate_claim_annotations(ann_89, {"c1": "sha256-draft-c1-hash"})
        assert res_89["total_claims"] == 100
        assert res_89["supported_claims"] == 89
        assert res_89["supported_claims_ratio"] == 0.89
        assert res_89["grounded_claims_gate_passed"] is False

        # 90 supported, 10 unsupported
        ann_90 = [
            {
                "case_id": "c1",
                "draft_sha256": "sha256-draft-c1-hash",
                "reviewer": "eval_lead",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "attestation": {"all_factual_claims_identified": True},
                "claims": (
                    [{"claim_id": f"s_{i}", "verdict": "supported"} for i in range(90)]
                    + [{"claim_id": f"u_{i}", "verdict": "unsupported"} for i in range(10)]
                ),
            }
        ]
        res_90 = evaluate_claim_annotations(ann_90, {"c1": "sha256-draft-c1-hash"})
        assert res_90["supported_claims"] == 90
        assert res_90["supported_claims_ratio"] == 0.90
        assert res_90["grounded_claims_gate_passed"] is True

    def test_unknown_verdict_counted_as_unsupported(self):
        """Claims marked 'unknown' must be counted in denominator as unsupported."""
        ann = [
            {
                "case_id": "c1",
                "draft_sha256": "sha256-draft-c1-hash",
                "reviewer": "eval_lead",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "attestation": {"all_factual_claims_identified": True},
                "claims": [
                    {"claim_id": "c1_1", "verdict": "supported"},
                    {"claim_id": "c1_2", "verdict": "unknown"},  # Treated as unsupported
                ],
            }
        ]
        res = evaluate_claim_annotations(ann, {"c1": "sha256-draft-c1-hash"})
        assert res["total_claims"] == 2
        assert res["supported_claims"] == 1
        assert res["unknown_claims"] == 1
        assert res["supported_claims_ratio"] == 0.5

    def test_draft_hash_mismatch_raises_evaluation_error(self):
        """Annotation referencing an outdated or tampered draft hash must be rejected."""
        ann = [
            {
                "case_id": "c1",
                "draft_sha256": "wrong-hash-1234",
                "reviewer": "eval_lead",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "claims": [{"claim_id": "c1_1", "verdict": "supported"}],
            }
        ]
        with pytest.raises(EvaluationError, match="Draft hash mismatch"):
            evaluate_claim_annotations(ann, {"c1": "sha256-draft-c1-hash"})

    def test_zero_claims_without_rationale_rejected(self):
        """Draft marked with 0 claims without reviewer rationale fails with insufficient_evidence."""
        ann = [
            {
                "case_id": "c1",
                "draft_sha256": "sha256-draft-c1-hash",
                "reviewer": "eval_lead",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "claims": [],  # zero claims!
                "attestation": {"all_factual_claims_identified": True, "rationale": None},
            }
        ]
        res = evaluate_claim_annotations(ann, {"c1": "sha256-draft-c1-hash"})
        assert res["status"] == "insufficient_evidence"
        assert res["grounded_claims_gate_passed"] is False

    def test_missing_reviewer_raises_evaluation_error(self):
        """Missing or blank reviewer string must raise EvaluationError."""
        ann = [
            {
                "case_id": "c1",
                "draft_sha256": "sha256-draft-c1-hash",
                "reviewer": "  ",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "claims": [{"claim_id": "c1_1", "verdict": "supported"}],
            }
        ]
        with pytest.raises(EvaluationError, match="Missing reviewer"):
            evaluate_claim_annotations(ann, {"c1": "sha256-draft-c1-hash"})


class TestAssessRunWorkflow:
    def test_assess_run_success_creates_immutable_assessment(self, mock_run_dir, tmp_path):
        """assess_run creates new assessment directory with snapshot and manifest."""
        ann_file = tmp_path / "annotations.jsonl"
        ann = {
            "case_id": "c1",
            "draft_sha256": "sha256-draft-c1-hash",
            "reviewer": "eval_lead",
            "reviewed_at": "2026-11-05T00:00:00Z",
            "attestation": {"all_factual_claims_identified": True},
            "claims": [{"claim_id": "c1_1", "verdict": "supported"}],
        }
        ann_file.write_text(json.dumps(ann) + "\n", encoding="utf-8")

        assessment_dir = assess_run(
            run_dir=mock_run_dir,
            annotations_path=ann_file,
            assessment_id="review-001",
        )
        assert assessment_dir.exists()
        assert (assessment_dir / "annotations.snapshot.jsonl").exists()
        assert (assessment_dir / "assessment_manifest.json").exists()
        assert (assessment_dir / "assessment_metrics.json").exists()

        # Attempting to re-run with same assessment_id must refuse to overwrite
        with pytest.raises(EvaluationError, match="already exists"):
            assess_run(
                run_dir=mock_run_dir,
                annotations_path=ann_file,
                assessment_id="review-001",
            )

    def test_assess_run_detects_tampered_run_manifest(self, mock_run_dir, tmp_path):
        """If run artifact was altered after run manifest creation, assess_run must raise."""
        # Tamper results.jsonl
        results_file = mock_run_dir / "results.jsonl"
        results_file.write_text("tampered content\n", encoding="utf-8")

        ann_file = tmp_path / "annotations.jsonl"
        ann_file.write_text("{}\n", encoding="utf-8")

        with pytest.raises(EvaluationError, match="checksum mismatch"):
            assess_run(
                run_dir=mock_run_dir,
                annotations_path=ann_file,
                assessment_id="review-002",
            )


class TestProductSessions:
    def test_negative_or_nonfinite_duration_raises_error(self, tmp_path):
        """Duration <= 0 or NaN/inf must raise EvaluationError."""
        csv_file = tmp_path / "sessions.csv"
        csv_content = (
            "participant_id,task_id,condition,trial_order,duration_seconds,outcome,feedback_action,draft_hash\n"
            "p1,task_1,manual,1,-5.0,completed,approve,hash1\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        with pytest.raises(EvaluationError, match="Invalid duration"):
            evaluate_product_sessions(csv_file)

    def test_approval_rate_not_labeled_as_time_saved(self, tmp_path):
        """Approval rate and time metrics must remain strictly separate."""
        csv_file = tmp_path / "sessions.csv"
        csv_content = (
            "participant_id,task_id,condition,trial_order,duration_seconds,outcome,feedback_action,draft_hash\n"
            "p1,task_1,manual,1,100.0,completed,approve,hash1\n"
            "p1,task_1,copilot,2,40.0,completed,approve,hash1\n"
            "p2,task_2,manual,2,120.0,completed,approve,hash2\n"
            "p2,task_2,copilot,1,50.0,completed,edit,hash2\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        metrics = evaluate_product_sessions(csv_file)
        assert "approval_rate" in metrics
        assert "paired_time_saved_median_seconds" in metrics
        # Strictly verify approval rate is not named or used as time saved
        assert "approval_time_saved" not in metrics
        assert metrics["paired_time_saved_median_seconds"] == 65.0  # (100-40=60, 120-50=70 -> median=65)
        assert metrics["approval_rate"] == 0.5  # 1 approved out of 2 copilot sessions

    def test_missing_paired_tasks_returns_insufficient_evidence(self, tmp_path):
        """Unpaired sessions cannot compute paired product value."""
        csv_file = tmp_path / "sessions.csv"
        csv_content = (
            "participant_id,task_id,condition,trial_order,duration_seconds,outcome,feedback_action,draft_hash\n"
            "p1,task_1,manual,1,100.0,completed,approve,hash1\n"
            "p2,task_2,copilot,1,40.0,completed,approve,hash2\n"
        )
        csv_file.write_text(csv_content, encoding="utf-8")

        metrics = evaluate_product_sessions(csv_file)
        assert metrics["status"] == "insufficient_evidence"
        assert metrics["paired_time_saved_median_seconds"] == "N/A"
