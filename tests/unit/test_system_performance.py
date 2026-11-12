"""Unit tests for BudgetLedger atomic reservations, budget enforcement, and latency measurement."""

import pytest
import sqlite3
from pathlib import Path

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_performance import (
    BudgetLedger,
    measure_system_latency,
)


@pytest.fixture
def sample_config():
    return SystemConfig(
        max_llm_calls=5,
        max_estimated_cost_usd=1.0,
        pricing={
            "currency": "USD",
            "input_per_million": 0.50,
            "output_per_million": 1.50,
        },
        warmup_requests=2,
        latency_requests=10,
    )


class TestBudgetLedger:
    def test_reserve_and_record_lifecycle(self, sample_config, tmp_path):
        """BudgetLedger reserves calls atomically and records actual usage idempotently."""
        db_path = tmp_path / "budget.sqlite3"
        ledger = BudgetLedger(db_path=db_path, config=sample_config)

        # 1. Reserve call 1
        att_1 = ledger.reserve(input_token_bound=1000, output_token_bound=500)
        assert att_1 is not None

        # 2. Record usage
        ledger.record(att_1, usage={"prompt_tokens": 800, "completion_tokens": 400})
        # Duplicate record call is idempotent
        ledger.record(att_1, usage={"prompt_tokens": 800, "completion_tokens": 400})

        summary = ledger.summary()
        assert summary["reserved_calls"] == 1
        assert summary["completed_calls"] == 1
        assert summary["remaining_calls"] == 4
        assert summary["budget_exhausted"] is False

    def test_max_llm_calls_enforced(self, sample_config, tmp_path):
        """Reserving past max_llm_calls raises EvaluationError."""
        db_path = tmp_path / "budget_max.sqlite3"
        ledger = BudgetLedger(db_path=db_path, config=sample_config)

        # Reserve 5 calls (reaching max)
        for _ in range(5):
            ledger.reserve(input_token_bound=100, output_token_bound=100)

        # 6th call must be blocked
        with pytest.raises(EvaluationError, match="Budget exhausted|max LLM calls"):
            ledger.reserve(input_token_bound=100, output_token_bound=100)

    def test_missing_pricing_rejects_usd_cap_mode(self, tmp_path):
        """Configuring max_estimated_cost_usd without pricing details raises EvaluationError."""
        db_path = tmp_path / "budget_nopricing.sqlite3"
        cfg = SystemConfig(max_estimated_cost_usd=1.0, pricing=None)

        with pytest.raises(EvaluationError, match="pricing"):
            BudgetLedger(db_path=db_path, config=cfg)

    def test_unknown_usage_keeps_reservation_cost_flagged(self, sample_config, tmp_path):
        """Failed attempt with None usage preserves reservation and flags unknown cost."""
        db_path = tmp_path / "budget_unknown.sqlite3"
        ledger = BudgetLedger(db_path=db_path, config=sample_config)

        att = ledger.reserve(input_token_bound=500, output_token_bound=500)
        ledger.record(att, usage=None)

        summary = ledger.summary()
        assert summary["reserved_calls"] == 1
        assert summary["has_unknown_cost"] is True


class TestLatencyMeasurement:
    def test_warmup_separated_from_latency_p95(self, tmp_path):
        """Warm-up requests are not merged into warm p95 metrics."""
        from pipeline.evaluation.system_execution import build_system_dependencies

        cases = [
            SystemCase(
                id=f"case-lat-{i:02d}",
                primary_slice="supported",
                text=f"Sample query {i}",
                true_intent="track_order",
                context=SystemCaseContext(ticket_customer_id=f"cust-{i}"),
                expected=SystemCaseExpected(actions=["retrieve_draft"]),
            )
            for i in range(10)
        ]
        cfg = SystemConfig(warmup_requests=2, latency_requests=5)
        inputs = VerifiedSystemInputs(
            cases=cases,
            config=cfg,
            source_paths={},
            input_hashes={},
            as_of=None,
            coverage={},
            manifest={"status": "approved"},
        )
        runtime_dir = tmp_path / "runtime_lat"
        runtime_dir.mkdir()
        deps = build_system_dependencies(inputs, profile="mock", runtime_dir=runtime_dir)

        results = measure_system_latency(inputs, deps)
        # 5 latency results returned
        assert len(results) == 5
        for r in results:
            assert r.total_elapsed_ms > 0

        deps.close()
