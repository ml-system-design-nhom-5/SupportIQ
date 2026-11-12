"""Reproduction and regression probes for the 10 system evaluation review findings."""

from tests.annotation_fixtures import reviewed_annotations

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
    load_system_inputs,
)
from pipeline.evaluation.system_execution import (
    build_system_dependencies,
    execute_system_case,
)
from pipeline.evaluation.system_metrics import (
    aggregate_system_metrics,
    evaluate_system_gates,
)
from pipeline.evaluation.system_performance import BudgetLedger


@pytest.fixture
def sample_verified_inputs(tmp_path):
    cases = [
        SystemCase(
            id="case-ret-01",
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
            id="case-esc-01",
            primary_slice="supported",
            tags=["sensitive"],
            text="Close my account please",
            true_intent="close_account",
            context=SystemCaseContext(ticket_customer_id="cust-002"),
            expected=SystemCaseExpected(
                actions=["escalate"],
                must_escalate=True,
                answerable=False,
            ),
        ),
    ]
    config = SystemConfig(
        deadline_seconds=2.0,
        max_llm_calls=50,
        max_estimated_cost_usd=0.01,
        pricing={
            "model": "gemini-3.1-flash-lite",
            "currency": "USD",
            "input_cost_per_million": 0.075,
            "output_cost_per_million": 0.30,
        },
        mandatory_gates=[
            "ml_macro_f1",
            "routing_guardrails",
            "retrieval_safety",
            "retrieval_recall_at_3",
            "grounded_claims",
            "oversight_compliance",
            "live_warm_p95_seconds",
        ],
        thresholds={
            "ml_macro_f1": 0.85,
            "recall_at_3": 0.80,
            "grounded_claims": 0.90,
            "warm_p95_seconds": 12.0,
            "guardrail_accuracy": 1.00,
        },
    )
    return VerifiedSystemInputs(
        cases=cases,
        config=config,
        source_paths={},
        input_hashes={},
        as_of=datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc),
        coverage={"kb_coverage_gap": False},
        manifest={"status": "approved"},
    )


class TestSystemReviewProbes:
    def test_probe_1_live_profile_preflight_and_readiness(self, sample_verified_inputs, tmp_path):
        """P1 Finding 1: Live profile must not unconditionally throw preflight error when manifest exists."""
        runtime_dir = tmp_path / "runtime_live"
        runtime_dir.mkdir()

        # Without manifest, it must raise missing manifest
        with patch.object(Path, "exists", return_value=False):
            with pytest.raises(EvaluationError, match="manifest.*not found"):
                build_system_dependencies(sample_verified_inputs, profile="live", runtime_dir=runtime_dir)

        # When manifest and readiness checks pass, live profile builds successfully
        manifest_mock = {
            "package_version": "1.0.0",
            "model_type": "hybrid",
            "status": "ready",
            "artifacts": {"model": {"path": "model.onnx", "sha256": "dummy_sha"}},
        }
        from io import StringIO
        orig_open = open
        def _mocked_open(file, *args, **kwargs):
            if "manifest.json" in str(file):
                return StringIO(json.dumps(manifest_mock))
            return orig_open(file, *args, **kwargs)

        mock_server = MagicMock()
        mock_server.start.return_value = "http://127.0.0.1:8999"

        with patch.object(Path, "exists", return_value=True), \
             patch("builtins.open", side_effect=_mocked_open), \
             patch("pipeline.evaluation.system_execution.compute_sha256", return_value="dummy_sha"), \
             patch("pipeline.evaluation.system_execution.ManagedDemoServer", return_value=mock_server), \
             patch("apps.core_backend.retrieval.adapter.RetrievalAdapter.__init__", return_value=None), \
             patch("apps.core_backend.intent.client.IntentClient.__init__", return_value=None):
            deps = build_system_dependencies(sample_verified_inputs, profile="live", runtime_dir=runtime_dir)
            assert deps.profile == "live"
            assert deps.managed_server is not None
            deps.close()

    def test_probe_2_mock_profile_blocks_real_encoder_and_gemini_client(self, sample_verified_inputs, monkeypatch, tmp_path):
        """P1 Finding 2: Mock profile must not call real PolicyEncoder or read GEMINI_API_KEY from environment."""
        monkeypatch.setenv("GEMINI_API_KEY", "secret-live-api-key-12345")
        runtime_dir = tmp_path / "runtime_mock_isolated"
        runtime_dir.mkdir()

        with patch("apps.core_backend.retrieval.encoder.PolicyEncoder.__init__") as mock_encoder_init, \
             patch("apps.core_backend.llm.gemini.GeminiDraftClient.generate") as mock_gemini_gen:
            deps = build_system_dependencies(sample_verified_inputs, profile="mock", runtime_dir=runtime_dir)
            # Real heavy PolicyEncoder constructor must NOT be called in mock profile
            mock_encoder_init.assert_not_called()

            case = sample_verified_inputs.cases[0]
            execute_system_case(case, deps, attempt_id="att-iso", scope="e2e")
            # Gemini real generate must NEVER be reached in mock profile
            mock_gemini_gen.assert_not_called()
            deps.close()

    def test_probe_3_grounding_rejects_invented_case_and_requires_mandatory_draft_coverage(self):
        """P1 Finding 3: Grounding must reject annotations for non-existent cases and require full draft coverage."""
        expected_hashes = {
            "case-01": "hash001",
            "case-02": "hash002",
        }

        # Case A: Annotation for non-existent case ID must raise EvaluationError
        bad_annotations = [
            {
                "case_id": "invented-case-999",
                "draft_sha256": "wronghash",
                "reviewer": "rev1",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "claims": [{"claim_text": "text", "verdict": "supported"}],
            }
        ]
        with pytest.raises(EvaluationError, match="undeclared|unknown|non-existent"):
            evaluate_claim_annotations(reviewed_annotations(bad_annotations), expected_hashes)

        # Case B: Incomplete annotation of mandatory draft cases yields insufficient_evidence
        partial_annotations = [
            {
                "case_id": "case-01",
                "draft_sha256": "hash001",
                "reviewer": "rev1",
                "reviewed_at": "2026-11-05T00:00:00Z",
                "claims": [{"claim_text": "text", "verdict": "supported"}],
            }
        ]
        # case-02 is missing from annotations
        res = evaluate_claim_annotations(
            reviewed_annotations(partial_annotations),
            expected_hashes,
            expected_draft_case_ids={"case-01", "case-02"},
        )
        assert res["status"] == "insufficient_evidence"
        assert res["grounded_claims_gate_passed"] is False

    def test_probe_4_retrieval_safety_independently_verifies_kb_metadata(self):
        """P1 Finding 4: Independent verification against pinned KB snapshot flags expired or invalid docs."""
        cases = [
            SystemCase(
                id="c-1",
                primary_slice="supported",
                tags=[],
                text="query",
                true_intent="return_policy",
                context=SystemCaseContext(ticket_customer_id="cust-1"),
                expected=SystemCaseExpected(actions=["retrieve_draft"], answerable=True, gold_sources=[{"doc_id": "KB-1", "version": "1.0"}]),
            )
        ]
        # Runner output falsely claims status="approved", but doc version is 99.0 which is not in KB snapshot
        results = [
            CaseResult(
                case_id="c-1",
                repetition=1,
                profile="mock",
                scope="e2e",
                execution_status="ok",
                sources=[{"doc_id": "KB-1", "version": "99.0", "status": "approved"}],
            )
        ]
        kb_snapshot = {
            ("KB-1", "1.0"): {
                "doc_id": "KB-1",
                "version": "1.0",
                "status": "approved",
                "allowed_roles": ["agent"],
                "valid_from": "2026-01-01T00:00:00Z",
                "valid_to": "2026-12-31T23:59:59Z",
            }
        }
        metrics = aggregate_system_metrics(cases, results, kb_snapshot=kb_snapshot, as_of=datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc))
        assert metrics["retrieval"]["safety_violations"] >= 1
        assert metrics["retrieval"]["safety_guardrail_passed"] is False

    def test_probe_5_budget_ledger_enforces_usd_cap_and_factory_wires_it(self, sample_verified_inputs, tmp_path):
        """P2 Finding 5: USD budget cap must reject excessive reservations and factory must wire ledger."""
        db_path = tmp_path / "budget_probe.sqlite3"
        ledger = BudgetLedger(db_path=db_path, config=sample_verified_inputs.config)
        # 1,000,000 input tokens at $0.075 / 1M = $0.075, which exceeds max_estimated_cost_usd ($0.01)
        with pytest.raises(EvaluationError, match="Budget exhausted.*USD|cost cap"):
            ledger.reserve(input_token_bound=1_000_000, output_token_bound=0)

        # Factory must wire budget ledger
        runtime_dir = tmp_path / "runtime_ledger"
        runtime_dir.mkdir()
        deps = build_system_dependencies(sample_verified_inputs, profile="mock", runtime_dir=runtime_dir)
        assert deps.ledger is not None
        deps.close()

    def test_probe_6_deadline_terminates_hanging_runner_without_waiting(self, sample_verified_inputs, tmp_path):
        """P2 Finding 6: Hanging runner must be actively terminated at deadline, not waited out."""
        runtime_dir = tmp_path / "runtime_hard_timeout"
        runtime_dir.mkdir()
        deps = build_system_dependencies(sample_verified_inputs, profile="mock", runtime_dir=runtime_dir)
        deps.deadline_seconds = 0.05
        from pipeline.evaluation.isolated_call import IsolatedCaller
        deps.isolated_caller = IsolatedCaller()
        deps.isolated_caller.call(lambda: None, {}, 2)

        def _hanging_run(*args, **kwargs):
            time.sleep(0.4)
            return {"action": "retrieve_draft"}

        case = sample_verified_inputs.cases[0]
        t0 = time.perf_counter()
        with patch.object(deps.runner, "run", side_effect=_hanging_run):
            res = execute_system_case(case, deps, attempt_id="att-hang", scope="e2e")
        t_elapsed = time.perf_counter() - t0

        # Must abort around deadline (0.05s) rather than waiting full 0.4s
        assert t_elapsed < 0.25
        assert res.execution_status == "timeout"
        assert res.error_code == "deadline_exceeded"
        deps.close()

    def test_probe_7_quality_gates_evaluate_all_mandatory_gates(self, sample_verified_inputs):
        """P2 Finding 7: Quality gates must evaluate retrieval_recall_at_3, live_warm_p95_seconds, oversight_compliance."""
        perfect_metrics = {
            "routing": {"must_escalate_total": 5, "guardrail_passed": True},
            "retrieval": {"safety_violations": 0, "recall_at_3": 0.95, "recall_at_3_raw": 0.95, "answerable_count": 10},
            "human_assessment": {"status": "pass", "supported_claims_ratio": 0.95, "supported_claims_ratio_raw": 0.95},
            "ml": {"macro_f1": 0.90},
            "latency": {"warm_p95_seconds": 2.5},
            "oversight": {"total_scenarios": 3, "passed_scenarios": 3, "status": "pass"},
        }
        res = evaluate_system_gates(perfect_metrics, sample_verified_inputs.config, evidence_kind="live")
        # All mandatory gates in config must be evaluated and passed
        for g_name in sample_verified_inputs.config.mandatory_gates:
            assert g_name in res["gates"], f"Gate '{g_name}' missing from evaluated gates"
            assert res["gates"][g_name]["status"] == "pass", f"Gate '{g_name}' failed: {res['gates'][g_name]}"
        assert res["all_mandatory_passed"] is True

    def test_probe_8_fault_injection_and_must_not_draft_check(self, sample_verified_inputs, tmp_path):
        """P2 Finding 8: Fault injection covers all scenarios and enforces must_not_draft."""
        runtime_dir = tmp_path / "runtime_faults"
        runtime_dir.mkdir()
        deps = build_system_dependencies(sample_verified_inputs, profile="mock", runtime_dir=runtime_dir)

        # 1. Fault case with llm_error should not generate a draft
        fault_case = SystemCase(
            id="c-fault-1",
            primary_slice="uncertainty_and_faults",
            tags=["fault"],
            text="Help me return this",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-1"),
            expected=SystemCaseExpected(
                actions=["escalate", "manual_fallback"],
                must_not_draft=True,
                answerable=False,
            ),
            fault="llm_error",
        )
        res = execute_system_case(fault_case, deps, attempt_id="att-fault", scope="e2e")
        assert res.draft_body is None
        assert res.final_action in ("escalate", "manual_fallback")

        # 2. Case with must_not_draft=True where a draft is produced should be flagged
        violating_case = SystemCase(
            id="c-violating-1",
            primary_slice="uncertainty_and_faults",
            tags=["fault"],
            text="Help me cancel order",
            true_intent="cancel_order",
            context=SystemCaseContext(ticket_customer_id="cust-1"),
            expected=SystemCaseExpected(
                actions=["escalate"],
                must_not_draft=True,
                answerable=False,
            ),
        )
        with patch.object(deps.runner, "run", return_value={"action": "retrieve_draft", "draft_body": "Unexpected draft"}):
            violating_res = execute_system_case(violating_case, deps, attempt_id="att-violate", scope="e2e")
            # Must record safety violation or error status when must_not_draft is violated
            assert violating_res.execution_status == "error" or violating_res.error_code == "must_not_draft_violation"

        deps.close()

    def test_probe_9_unrounded_comparisons_prevent_false_pass(self, sample_verified_inputs):
        """P2 Finding 9: Unrounded comparisons must reject 16000/20001 for 0.80 and 89999/100000 for 0.90."""
        # 16000 / 20001 = 0.7999600019999
        raw_recall = 16000 / 20001
        metrics = {
            "routing": {"must_escalate_total": 1, "guardrail_passed": True},
            "retrieval": {"safety_violations": 0, "recall_at_3": round(raw_recall, 2), "recall_at_3_raw": raw_recall, "answerable_count": 20001},
            "human_assessment": {"status": "pass", "supported_claims_ratio": 0.90, "supported_claims_ratio_raw": 89999 / 100000},
            "ml": {"macro_f1": 0.90},
            "latency": {"warm_p95_seconds": 2.5},
            "oversight": {"status": "pass"},
        }
        res = evaluate_system_gates(metrics, sample_verified_inputs.config, evidence_kind="live")
        assert res["gates"]["retrieval_recall_at_3"]["status"] == "fail"
        assert res["gates"]["grounded_claims"]["status"] == "fail"

    def test_probe_10_assessment_rejects_missing_manifest_files(self, tmp_path):
        """P2 Finding 10: assess_completed_run must reject manifest without files or missing mandatory artifacts."""
        run_dir = tmp_path / "run_empty_manifest"
        run_dir.mkdir()
        manifest_path = run_dir / "manifest.json"
        manifest_path.write_text(json.dumps({"schema_version": "v1.0", "files": {}}), encoding="utf-8")

        with pytest.raises(EvaluationError, match="manifest.*files|mandatory"):
            assess_run(run_dir=run_dir, annotations_path=tmp_path / "fake.jsonl", assessment_id="ass-1")

    def test_probe_additional_run_state_marked_failed_on_init_error(self, tmp_path):
        """Additional: run_state.json must be marked 'failed' if dependencies build fails."""
        from pipeline.evaluation.run_system_evaluation import run_system_evaluation
        suite_path = Path("data/benchmarks/system/v1/suite_manifest.json")
        config_path = Path("pipeline/configs/system_evaluation.json")

        out_root = tmp_path / "eval_out"
        out_root.mkdir()

        # Patch build_system_dependencies to fail
        with patch("pipeline.evaluation.run_system_evaluation.build_system_dependencies", side_effect=ValueError("Boom")):
            with pytest.raises(ValueError, match="Boom"):
                run_system_evaluation(
                    suite_path=suite_path,
                    config_path=config_path,
                    profile="mock",
                    run_id="run-init-fail-001",
                    output_root=out_root,
                )

        state_file = out_root / "run-init-fail-001" / "run_state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["status"] == "failed"
        assert "Boom" in state.get("error", "")

    def test_probe_additional_kb_coverage_gap_reflects_kb_evidence(self):
        """Additional: kb_coverage_gap must reflect KB documents coverage of core intents, not query intents."""
        # Using the actual benchmark suite inputs
        inputs = load_system_inputs(
            repo_root=Path("."),
            suite_path=Path("data/benchmarks/system/v1/suite_manifest.json"),
            config_path=Path("pipeline/configs/system_evaluation.json"),
            profile="mock",
        )
        # Even though query texts contain all 12 core intents, KB approved snapshot covers only 3 intents
        # so kb_coverage_gap MUST be True!
        assert inputs.coverage["kb_coverage_gap"] is True
        assert len(inputs.coverage.get("missing_core_kb_intents", [])) > 0
