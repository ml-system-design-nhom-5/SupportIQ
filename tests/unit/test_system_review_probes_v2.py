"""Reproduction and regression probes v2 for the 6 verified review findings:
1. [P1] Timeout stops background worker (no post-deadline side effects).
2. [P1] Live preflight validates release manifest schema/checksums and starts managed server.
3. [P1] Grounding rejects run when expected draft case is missing draft or annotation.
4. [P2] Valid sources with dates are not miscounted as safety violations (datetime import/scoping).
5. [P2] Duplicate annotations are deduplicated and cannot artificially inflate grounding ratio.
6. [P2] Controlled fault injection for encoder and commerce components.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.assess_system import (
    assess_run,
    evaluate_claim_annotations,
)
from pipeline.evaluation.system_contracts import (
    CaseResult,
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_execution import (
    SystemDependencies,
    build_system_dependencies,
    execute_system_case,
)
from pipeline.evaluation.system_metrics import aggregate_system_metrics
from pipeline.preparation.utils import compute_sha256


@pytest.fixture
def base_verified_inputs(tmp_path):
    cases = [
        SystemCase(
            id="case-draft-01",
            primary_slice="supported",
            tags=["policy"],
            text="What is the return window?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-001"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-01", "version": "1.0"}],
                draft_expected=True,
            ),
        ),
        SystemCase(
            id="case-draft-02",
            primary_slice="supported",
            tags=["policy"],
            text="How much is shipping?",
            true_intent="shipping_costs",
            context=SystemCaseContext(ticket_customer_id="cust-002"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-02", "version": "1.0"}],
                draft_expected=True,
            ),
        ),
    ]

    kb_file = tmp_path / "approved_kb.v1.json"
    kb_data = [
        {
            "doc_id": "KB-01",
            "document_id": "KB-01",
            "version": "1.0",
            "status": "approved",
            "title": "Return Policy",
            "content": "Return within 30 days.",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
        },
        {
            "doc_id": "KB-02",
            "document_id": "KB-02",
            "version": "1.0",
            "status": "approved",
            "title": "Shipping Policy",
            "content": "Shipping costs 5 dollars.",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
        },
    ]
    kb_file.write_text(json.dumps(kb_data), encoding="utf-8")

    suite_file = tmp_path / "suite.manifest.json"
    suite_data = {
        "schema_version": "v1.0",
        "status": "candidate",
        "as_of": "2026-06-01T00:00:00Z",
        "files": {
            "cases": {"path": "cases.jsonl", "sha256": "dummy"},
            "kb": {"path": "approved_kb.v1.json", "sha256": compute_sha256(kb_file)},
        },
    }
    suite_file.write_text(json.dumps(suite_data), encoding="utf-8")

    return VerifiedSystemInputs(
        cases=cases,
        config=SystemConfig(),
        source_paths={"suite_manifest": suite_file, "kb": kb_file},
        input_hashes={
            "suite_manifest": compute_sha256(suite_file),
            "kb": compute_sha256(kb_file),
        },
        as_of=datetime(2026, 6, 1, tzinfo=timezone.utc),
        coverage={},
        manifest=suite_data,
    )


class TestReviewFinding1WorkerTimeoutTermination:
    def test_timeout_stops_worker_thread_preventing_side_effects(self, base_verified_inputs, tmp_path):
        """Worker executing beyond deadline terminates managed worker process cleanly without PyThreadState_SetAsyncExc."""
        mock_server = MagicMock()
        mock_server.is_running.return_value = True

        class SlowSideEffectRunner:
            def run(self, text, context, run_id=None):
                time.sleep(0.08)
                return {"routing_action": "retrieve_draft", "action": "retrieve_draft"}

        deps = SystemDependencies(
            runner=SlowSideEffectRunner(),
            retrieval=MagicMock(),
            store=MagicMock(),
            demo_app=MagicMock(),
            profile="mock",
            runtime_dir=tmp_path,
            clock=lambda: datetime(2026, 6, 1, tzinfo=timezone.utc),
            deadline_seconds=0.02,
            managed_server=mock_server,
        )

        case = base_verified_inputs.cases[0]
        res = execute_system_case(case, deps, attempt_id="attempt-timeout", scope="e2e")

        assert res.execution_status == "timeout"
        assert res.error_code == "deadline_exceeded"

        # Worker process must be terminated and restarted cleanly without async exception injection
        assert mock_server.close.called, "Managed worker process was not terminated on timeout!"
        assert mock_server.restart.called, "Managed worker process was not restarted after timeout!"


class TestReviewFinding2LivePreflightVerification:
    def test_live_preflight_rejects_empty_or_incomplete_manifest(self, base_verified_inputs, tmp_path, monkeypatch):
        """Live profile must reject release manifest with missing package_version, model_type, or artifacts."""
        monkeypatch.chdir(tmp_path)
        rel_dir = tmp_path / "ml" / "releases"
        rel_dir.mkdir(parents=True)
        rel_file = rel_dir / "manifest.json"

        # 1. Empty dictionary manifest
        rel_file.write_text("{}", encoding="utf-8")
        with pytest.raises(EvaluationError, match="missing required fields|invalid release"):
            build_system_dependencies(base_verified_inputs, profile="live", runtime_dir=tmp_path / "run_live")

        # 2. Manifest missing artifacts
        rel_file.write_text(
            json.dumps({"package_version": "1.0.0", "model_type": "intent_linear"}),
            encoding="utf-8",
        )
        with pytest.raises(EvaluationError, match="missing required fields|artifacts"):
            build_system_dependencies(base_verified_inputs, profile="live", runtime_dir=tmp_path / "run_live")

    def test_live_preflight_verifies_artifact_checksums_and_starts_managed_server(
        self, base_verified_inputs, tmp_path, monkeypatch
    ):
        """Live profile verifies artifact checksums and instantiates/starts ManagedDemoServer."""
        monkeypatch.chdir(tmp_path)
        rel_dir = tmp_path / "ml" / "releases"
        rel_dir.mkdir(parents=True)

        artifact_file = rel_dir / "model.onnx"
        artifact_file.write_text("model-weights", encoding="utf-8")
        real_sha = compute_sha256(artifact_file)

        # Corrupted checksum
        rel_file = rel_dir / "manifest.json"
        rel_file.write_text(
            json.dumps({
                "package_version": "1.0.0",
                "model_type": "intent_onnx",
                "artifacts": {"model": {"path": "model.onnx", "sha256": "wrong-hash"}},
            }),
            encoding="utf-8",
        )
        with pytest.raises(EvaluationError, match="checksum mismatch"):
            build_system_dependencies(base_verified_inputs, profile="live", runtime_dir=tmp_path / "run_live")

        # Valid manifest -> starts managed server
        rel_file.write_text(
            json.dumps({
                "package_version": "1.0.0",
                "model_type": "intent_onnx",
                "artifacts": {"model": {"path": "model.onnx", "sha256": real_sha}},
            }),
            encoding="utf-8",
        )

        mock_server = MagicMock()
        mock_server.start.return_value = "http://127.0.0.1:8999"

        with patch("pipeline.evaluation.system_execution.ManagedDemoServer", return_value=mock_server):
            deps = build_system_dependencies(base_verified_inputs, profile="live", runtime_dir=tmp_path / "run_live")
            assert deps.profile == "live"
            assert deps.managed_server is not None
            mock_server.start.assert_called_once()
            deps.close()
            mock_server.close.assert_called_once()


class TestReviewFinding3GroundingMandatoryBenchmarkCases:
    def test_grounding_rejects_run_missing_draft_for_benchmark_case(self, tmp_path):
        """When benchmark expects 2 drafts but run only produced 1 draft, annotating the 1 draft must NOT pass grounding."""
        run_dir = tmp_path / "test_run"
        run_dir.mkdir()

        # Benchmark expects 2 drafts: c1 and c2
        r1 = {
            "case_id": "c1",
            "repetition": 1,
            "profile": "mock",
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
            "draft_body": "You have 30 days.",
            "draft_kind": "llm",
            "draft_hash": "hash-c1",
            "llm_called": True,
            "llm_metadata": None,
            "llm_usage": None,
            "stage_elapsed_ms": {},
            "total_elapsed_ms": 100.0,
            "audit_evidence": None,
        }
        # c2 failed to draft (clarify or escalate)
        r2 = {
            "case_id": "c2",
            "repetition": 1,
            "profile": "mock",
            "scope": "e2e",
            "execution_status": "ok",
            "error_code": None,
            "routing_action": "clarify",
            "final_action": "clarify",
            "requested_team": None,
            "target_queue": None,
            "reason_codes": ["low_margin"],
            "predicted_intent": "shipping_costs",
            "final_intent": "shipping_costs",
            "prediction_confidence": 0.5,
            "prediction_margin": 0.05,
            "sources": [],
            "draft_body": None,
            "draft_kind": None,
            "draft_hash": None,
            "llm_called": False,
            "llm_metadata": None,
            "llm_usage": None,
            "stage_elapsed_ms": {},
            "total_elapsed_ms": 100.0,
            "audit_evidence": None,
        }

        results_file = run_dir / "results.jsonl"
        results_file.write_text(json.dumps(r1) + "\n" + json.dumps(r2) + "\n", encoding="utf-8")

        manifest_file = run_dir / "manifest.json"
        manifest_data = {
            "schema_version": "v1.0",
            "run_id": "run-test-01",
            "profile": "mock",
            "status": "completed",
            "expected_draft_cases": ["c1", "c2"],  # Locked benchmark mandates drafts for c1 and c2
            "files": {
                "results.jsonl": {"path": "results.jsonl", "sha256": compute_sha256(results_file)},
            },
        }
        manifest_file.write_text(json.dumps(manifest_data), encoding="utf-8")

        # Annotation only for c1 (100% supported)
        ann_file = tmp_path / "annotations.jsonl"
        ann_file.write_text(
            json.dumps({
                "case_id": "c1",
                "draft_sha256": "hash-c1",
                "reviewer": "qa_lead",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "attestation": {"all_factual_claims_identified": True},
                "claims": [{"claim_id": "c1_1", "verdict": "supported"}],
            }) + "\n",
            encoding="utf-8",
        )

        assessment_dir = assess_run(run_dir, ann_file, assessment_id="assess-missing-draft")
        metrics_file = assessment_dir / "assessment_metrics.json"
        metrics = json.loads(metrics_file.read_text(encoding="utf-8"))

        claim_metrics = metrics["human_claim_metrics"]
        assert claim_metrics["status"] == "insufficient_evidence"
        assert claim_metrics["grounded_claims_gate_passed"] is False
        assert "c2" in claim_metrics["insufficient_reason"]


class TestReviewFinding4SafetyMetricsDateTime:
    def test_valid_approved_source_with_dates_has_zero_safety_violations(self, base_verified_inputs):
        """Approved source within validity dates must register exactly 0 safety violations."""
        case = base_verified_inputs.cases[0]
        case_res = CaseResult(
            case_id=case.id,
            repetition=1,
            profile="mock",
            scope="e2e",
            execution_status="ok",
            error_code=None,
            routing_action="retrieve_draft",
            final_action="retrieve_draft",
            predicted_intent="return_policy",
            final_intent="return_policy",
            prediction_confidence=0.95,
            prediction_margin=0.4,
            sources=[{"doc_id": "KB-01", "version": "1.0", "status": "approved"}],
            stage_elapsed_ms={},
            total_elapsed_ms=50.0,
        )

        kb_snapshot = {
            ("KB-01", "1.0"): {
                "doc_id": "KB-01",
                "version": "1.0",
                "status": "approved",
                "allowed_roles": ["agent"],
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": "2026-12-31T23:59:59Z",
            }
        }

        # Test with explicit as_of
        metrics = aggregate_system_metrics(
            cases=[case],
            results=[case_res],
            kb_snapshot=kb_snapshot,
            as_of=datetime(2026, 6, 1, tzinfo=timezone.utc),
        )
        assert metrics["retrieval"]["safety_violations"] == 0, f"Expected 0 violations, got {metrics['retrieval']['safety_violations']}"

        # Test with as_of=None (must use current datetime without NameError)
        metrics_none_asof = aggregate_system_metrics(
            cases=[case],
            results=[case_res],
            kb_snapshot=kb_snapshot,
            as_of=None,
        )
        assert metrics_none_asof["retrieval"]["safety_violations"] == 0


class TestReviewFinding5ClaimAnnotationDeduplication:
    def test_duplicate_claims_are_deduplicated_and_cannot_inflate_score(self):
        """Submitting 9 duplicate copies of a supported claim and 1 unsupported claim must yield 50% ratio, not 90%."""
        expected_hashes = {"c1": "sha-c1"}

        # 9 duplicates of claim 'claim-1' + 1 unsupported claim 'claim-2'
        duplicate_claims = [
            {"claim_id": "claim-1", "verdict": "supported"} for _ in range(9)
        ] + [
            {"claim_id": "claim-2", "verdict": "unsupported"}
        ]

        annotations = [
            {
                "case_id": "c1",
                "draft_sha256": "sha-c1",
                "reviewer": "evaluator",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "attestation": {"all_factual_claims_identified": True},
                "claims": duplicate_claims,
            }
        ]

        res = evaluate_claim_annotations(
            annotations,
            expected_draft_hashes=expected_hashes,
            expected_draft_case_ids={"c1"},
        )

        assert res["total_claims"] == 2
        assert res["supported_claims"] == 1
        assert res["unsupported_claims"] == 1
        assert res["supported_claims_ratio"] == 0.50
        assert res["grounded_claims_gate_passed"] is False
        assert res["status"] == "fail"


class TestReviewFinding6FaultInjectionsEncoderAndCommerce:
    @pytest.mark.parametrize("fault", ["encoder_unavailable", "encoder_failure"])
    def test_encoder_fault_injections_prevent_drafting(self, base_verified_inputs, tmp_path, fault):
        """When encoder fault is injected, retrieval must fail-closed and produce no draft."""
        deps = build_system_dependencies(base_verified_inputs, profile="mock", runtime_dir=tmp_path / "fault_enc")

        case = SystemCase(
            id=f"case-fault-{fault}",
            primary_slice="supported",
            tags=["policy"],
            text="What is the return window?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-001"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                draft_expected=True,
            ),
            fault=fault,
        )

        res = execute_system_case(case, deps, attempt_id=f"attempt-{fault}", scope="e2e")
        assert res.execution_status == "ok"
        assert res.draft_body is None, f"Expected no draft under fault {fault}, but got: {res.draft_body}"
        assert res.routing_action in ("retrieve_draft",)
        assert res.final_action in ("escalate", "clarify", "manual_fallback")

    @pytest.mark.parametrize("fault", ["commerce_unauthorized", "commerce_not_found"])
    def test_commerce_fault_injections_escalate_and_prevent_drafting(self, base_verified_inputs, tmp_path, fault):
        """When commerce fault is injected, order lookup must fail-closed and escalate to order_support without draft."""
        deps = build_system_dependencies(base_verified_inputs, profile="mock", runtime_dir=tmp_path / "fault_comm")

        case = SystemCase(
            id=f"case-fault-{fault}",
            primary_slice="supported",
            tags=["order"],
            text="Where is my order ORD-999?",
            true_intent="track_order",
            context=SystemCaseContext(
                ticket_customer_id="cust-001",
                extracted_slots={"order_id": "ORD-999"},
            ),
            expected=SystemCaseExpected(
                actions=["lookup_order"],
                must_escalate=True,
            ),
            fault=fault,
        )

        res = execute_system_case(case, deps, attempt_id=f"attempt-{fault}", scope="e2e")
        assert res.execution_status == "ok"
        assert res.draft_body is None
        assert res.final_action in ("escalate", "manual_fallback")
        assert res.requested_team in ("order_support", None)
