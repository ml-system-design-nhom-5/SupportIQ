"""Unit tests for System Execution adapter, dependencies factory, and case tracing."""

import time
import pytest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_execution import (
    build_system_dependencies,
    execute_system_case,
    SystemDependencies,
)


@pytest.fixture
def mock_verified_inputs(tmp_path):
    cases = [
        SystemCase(
            id="case-ret-01",
            primary_slice="supported",
            tags=["policy"],
            text="What is the return policy?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-001"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-RET-01", "version": "1.0"}],
                draft_expected=True,
            ),
        ),
        SystemCase(
            id="case-esc-01",
            primary_slice="supported",
            tags=["sensitive"],
            text="I want to close my account immediately",
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
        ml_timeout_seconds=0.5,
        llm_timeout_seconds=1.0,
    )
    return VerifiedSystemInputs(
        cases=cases,
        config=config,
        source_paths={},
        input_hashes={},
        as_of=datetime(2026, 11, 5, 0, 0, 0, tzinfo=timezone.utc),
        coverage={},
        manifest={"status": "approved"},
    )


class TestSystemDependenciesFactory:
    def test_mock_profile_does_not_call_network_or_read_live_keys(self, mock_verified_inputs, tmp_path):
        """Mock profile must not access network or require live Gemini credentials."""
        runtime_dir = tmp_path / "runtime_mock"
        runtime_dir.mkdir()

        # In mock profile, even with GEMINI_API_KEY absent or dummy, dependencies build cleanly
        with patch.dict("os.environ", {}, clear=True):
            deps = build_system_dependencies(mock_verified_inputs, profile="mock", runtime_dir=runtime_dir)
            assert deps.profile == "mock"
            assert deps.runtime_dir == runtime_dir
            assert (runtime_dir / "orchestration.sqlite3").exists()
            deps.close()

    def test_live_profile_stops_when_release_missing_or_unready(self, mock_verified_inputs, tmp_path):
        """Live profile stops preflight when external services or releases are unready."""
        runtime_dir = tmp_path / "runtime_live"
        runtime_dir.mkdir()

        # Keep the missing-release scenario independent of local deployed artifacts.
        original_exists = Path.exists
        with patch.object(Path, "exists", lambda p: False if p == Path("ml/releases/manifest.json") else original_exists(p)):
            with pytest.raises(EvaluationError, match="preflight|release|readiness"):
                build_system_dependencies(mock_verified_inputs, profile="live", runtime_dir=runtime_dir)


class TestExecuteSystemCase:
    def test_pipeline_runs_clarify_escalate_when_encoder_unavailable(self, mock_verified_inputs, tmp_path):
        """When encoder is unavailable, clarify/escalate queries still run and succeed."""
        runtime_dir = tmp_path / "runtime_enc_fail"
        runtime_dir.mkdir()
        deps = build_system_dependencies(mock_verified_inputs, profile="mock", runtime_dir=runtime_dir)

        # Force encoder to None/unavailable
        deps.retrieval.encoder = None
        deps.retrieval.encoder_error = "Model weights not found"

        esc_case = mock_verified_inputs.cases[1]
        result = execute_system_case(esc_case, deps, attempt_id="att-1", scope="e2e")
        assert result.execution_status == "ok"
        assert result.final_action == "escalate"
        deps.close()

    def test_deadline_terminates_hanging_request_and_records_timeout(self, mock_verified_inputs, tmp_path):
        """Case exceeding deadline_seconds records execution_status='timeout' and error_code='deadline_exceeded'."""
        runtime_dir = tmp_path / "runtime_timeout"
        runtime_dir.mkdir()
        deps = build_system_dependencies(mock_verified_inputs, profile="mock", runtime_dir=runtime_dir)

        # Configure short deadline on runtime deps
        deps.deadline_seconds = 0.1

        case = mock_verified_inputs.cases[0]
        # Simulate long execution by monkeypatching runner
        def _slow_run(*args, **kwargs):
            time.sleep(0.3)
            return {"action": "retrieve_draft"}

        with patch.object(deps.runner, "run", side_effect=_slow_run):
            result = execute_system_case(case, deps, attempt_id="att-slow", scope="e2e")
            assert result.execution_status == "timeout"
            assert result.error_code == "deadline_exceeded"

        deps.close()

    def test_case_result_records_routing_action_distinct_from_final_action(self, mock_verified_inputs, tmp_path):
        """CaseResult retains initial routing action and final action distinctly."""
        runtime_dir = tmp_path / "runtime_actions"
        runtime_dir.mkdir()
        deps = build_system_dependencies(mock_verified_inputs, profile="mock", runtime_dir=runtime_dir)

        case = mock_verified_inputs.cases[0]
        # In mock runner, return initial routing_action retrieve_draft and final_action escalate
        with patch.object(deps.runner, "run", return_value={
            "action": "escalate",
            "initial_routing_action": "retrieve_draft",
            "routing_action": "retrieve_draft",
            "predicted_intent": "return_policy",
            "final_intent": "return_policy",
            "reason_codes": ["insufficient_evidence"],
            "sources": [],
            "draft_body": None,
        }):
            result = execute_system_case(case, deps, attempt_id="att-actions", scope="e2e")
            assert result.routing_action == "retrieve_draft"
            assert result.final_action == "escalate"

        deps.close()

    def test_component_probe_uses_gold_intent_for_retrieval(self, mock_verified_inputs, tmp_path):
        """Retrieval component probe uses true_intent gold label, not classifier prediction."""
        runtime_dir = tmp_path / "runtime_probe"
        runtime_dir.mkdir()
        deps = build_system_dependencies(mock_verified_inputs, profile="mock", runtime_dir=runtime_dir)

        case = mock_verified_inputs.cases[0]
        with patch.object(deps.retrieval, "retrieve", return_value={"status": "success", "evidence": []}) as mock_ret:
            result = execute_system_case(case, deps, attempt_id="att-probe", scope="component")
            assert result.scope == "component"
            mock_ret.assert_called_once()
            args, kwargs = mock_ret.call_args
            # Gold intent "return_policy" must have been used
            assert args[1] == "return_policy" or kwargs.get("intent") == "return_policy"

        deps.close()
