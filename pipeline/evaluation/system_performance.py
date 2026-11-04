"""System latency measurement, budget ledger with atomic SQLite transactions, and performance profiling."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    CaseResult,
    SystemConfig,
    VerifiedSystemInputs,
)

if TYPE_CHECKING:
    from pipeline.evaluation.system_execution import SystemDependencies


class BudgetLedger:
    """Inter-process SQLite budget ledger enforcing call caps and token/USD cost limits atomically.
    Uses BEGIN IMMEDIATE transactions to prevent race conditions across parallel workers.
    """

    def __init__(self, db_path: Path | str, config: SystemConfig):
        self.db_path = Path(db_path).resolve()
        self.config = config
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Parse pricing configuration
        pricing = self.config.pricing or {}
        self.input_cost_per_million = float(
            pricing.get("input_cost_per_million") or pricing.get("input_per_million") or 0.0
        )
        self.output_cost_per_million = float(
            pricing.get("output_cost_per_million") or pricing.get("output_per_million") or 0.0
        )

        # Validate pricing requirements if USD cap is configured
        if self.config.max_estimated_cost_usd is not None:
            if self.input_cost_per_million <= 0.0 and self.output_cost_per_million <= 0.0:
                raise EvaluationError(
                    "Config specifies max_estimated_cost_usd but valid pricing details are missing"
                )

        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS budget_reservations (
                    attempt_id TEXT PRIMARY KEY,
                    reserved_at TEXT NOT NULL,
                    input_bound INTEGER NOT NULL,
                    output_bound INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    actual_usage_json TEXT
                )
                """
            )

    def reserve(self, input_token_bound: int, output_token_bound: int) -> str:
        """Atomically reserve budget for one outbound LLM attempt.
        Raises EvaluationError if max calls or cost caps are exhausted.
        """
        attempt_id = f"att-{uuid.uuid4()}"
        now_iso = datetime.now(timezone.utc).isoformat()

        conn = sqlite3.connect(self.db_path, isolation_level=None, timeout=10.0)
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT COUNT(*) FROM budget_reservations")
            count = cur.fetchone()[0]

            if count >= self.config.max_llm_calls:
                conn.execute("ROLLBACK")
                raise EvaluationError(
                    f"Budget exhausted: max LLM calls ({self.config.max_llm_calls}) reached"
                )

            # Check USD cost cap if configured
            new_res_cost = (
                (input_token_bound / 1e6) * self.input_cost_per_million
                + (output_token_bound / 1e6) * self.output_cost_per_million
            )
            if self.config.max_estimated_cost_usd is not None:
                cur = conn.execute(
                    "SELECT input_bound, output_bound, status, actual_usage_json FROM budget_reservations"
                )
                rows = cur.fetchall()
                current_cost = 0.0
                for r in rows:
                    ib, ob, st, usage_json = r
                    if st == "recorded" and usage_json:
                        try:
                            u = json.loads(usage_json)
                            in_tok = u.get("input_tokens", ib)
                            out_tok = u.get("output_tokens", ob)
                            current_cost += (
                                (in_tok / 1e6) * self.input_cost_per_million
                                + (out_tok / 1e6) * self.output_cost_per_million
                            )
                        except Exception:
                            current_cost += (
                                (ib / 1e6) * self.input_cost_per_million
                                + (ob / 1e6) * self.output_cost_per_million
                            )
                    else:
                        current_cost += (
                            (ib / 1e6) * self.input_cost_per_million
                            + (ob / 1e6) * self.output_cost_per_million
                        )

                projected_cost = current_cost + new_res_cost
                if projected_cost > self.config.max_estimated_cost_usd:
                    conn.execute("ROLLBACK")
                    raise EvaluationError(
                        f"Budget exhausted: max cost cap (${self.config.max_estimated_cost_usd:.4f}) exceeded (projected ${projected_cost:.4f})"
                    )

            # Insert reservation
            conn.execute(
                """
                INSERT INTO budget_reservations (
                    attempt_id, reserved_at, input_bound, output_bound, status, actual_usage_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (attempt_id, now_iso, input_token_bound, output_token_bound, "reserved", None),
            )
            conn.execute("COMMIT")
            return attempt_id
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            conn.close()

    def record(self, attempt_id: str, usage: Optional[Dict[str, Any]]) -> None:
        """Idempotently record actual provider usage for a completed attempt."""
        with sqlite3.connect(self.db_path, timeout=10.0) as conn:
            if usage is None:
                conn.execute(
                    """
                    UPDATE budget_reservations
                    SET status = 'unverified_usage'
                    WHERE attempt_id = ? AND status != 'recorded'
                    """,
                    (attempt_id,),
                )
            else:
                usage_json = json.dumps(usage, sort_keys=True)
                conn.execute(
                    """
                    UPDATE budget_reservations
                    SET status = 'recorded', actual_usage_json = ?
                    WHERE attempt_id = ?
                    """,
                    (usage_json, attempt_id),
                )

    def summary(self) -> Dict[str, Any]:
        """Return ledger usage statistics and remaining capacity."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM budget_reservations").fetchall()

        total_reserved = len(rows)
        completed = sum(1 for r in rows if r["status"] == "recorded")
        has_unknown = any(r["status"] != "recorded" for r in rows)
        remaining = max(0, self.config.max_llm_calls - total_reserved)
        exhausted = total_reserved >= self.config.max_llm_calls

        total_cost = 0.0
        for r in rows:
            ib = r["input_bound"]
            ob = r["output_bound"]
            u_json = r["actual_usage_json"]
            if r["status"] == "recorded" and u_json:
                try:
                    u = json.loads(u_json)
                    in_tok = u.get("input_tokens", ib)
                    out_tok = u.get("output_tokens", ob)
                    total_cost += (
                        (in_tok / 1e6) * self.input_cost_per_million
                        + (out_tok / 1e6) * self.output_cost_per_million
                    )
                except Exception:
                    total_cost += (
                        (ib / 1e6) * self.input_cost_per_million
                        + (ob / 1e6) * self.output_cost_per_million
                    )
            else:
                total_cost += (
                    (ib / 1e6) * self.input_cost_per_million
                    + (ob / 1e6) * self.output_cost_per_million
                )

        return {
            "reserved_calls": total_reserved,
            "completed_calls": completed,
            "max_llm_calls": self.config.max_llm_calls,
            "remaining_calls": remaining,
            "has_unknown_cost": has_unknown,
            "budget_exhausted": exhausted,
            "total_cost_usd": round(total_cost, 6) if (self.input_cost_per_million or self.output_cost_per_million) else None,
        }


def measure_system_latency(
    inputs: VerifiedSystemInputs,
    deps: SystemDependencies,
) -> List[CaseResult]:
    """Execute warm-up requests and measure system latency over representative cases.
    Ensures warm-up phase is strictly separated from warm p95 latency results.
    """
    from pipeline.evaluation.system_execution import execute_system_case

    cases = inputs.cases
    if not cases:
        return []

    # 1. Warm-up Phase
    warmup_count = inputs.config.warmup_requests
    for i in range(warmup_count):
        case = cases[i % len(cases)]
        attempt_id = f"warmup-{i:03d}-{uuid.uuid4().hex[:6]}"
        execute_system_case(case, deps, attempt_id=attempt_id, scope="e2e")

    # 2. Benchmark Phase
    latency_count = inputs.config.latency_requests
    latency_results: List[CaseResult] = []

    for i in range(latency_count):
        case = cases[i % len(cases)]
        attempt_id = f"lat-{i:04d}-{uuid.uuid4().hex[:6]}"
        res = execute_system_case(case, deps, attempt_id=attempt_id, scope="e2e")
        latency_results.append(res)

    return latency_results
