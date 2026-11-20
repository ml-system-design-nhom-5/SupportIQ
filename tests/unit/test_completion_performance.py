"""Unit tests for stage request timing, HTTP results summarization, and branch metrics (Task 6)."""

import pytest
from pipeline.evaluation.system_contracts import CaseResult
from pipeline.evaluation.system_performance import summarize_http_results


class TestHTTPPerformanceSummarization:
    def test_summarize_http_results_breaks_down_by_branch(self):
        """summarize_http_results reports all, llm-attempt, draft, no-llm latencies and coverage."""
        results = [
            # Case 1: Draft with LLM call (p95 latency)
            CaseResult(
                case_id="c1",
                repetition=1,
                profile="mock",
                scope="e2e",
                execution_status="ok",
                final_action="retrieve_draft",
                total_elapsed_ms=1200.0,
                stage_elapsed_ms={"classify_ms": 50.0, "llm_ms": 900.0, "retrieval_ms": 100.0},
            ),
            # Case 2: Draft with LLM call (faster)
            CaseResult(
                case_id="c2",
                repetition=1,
                profile="mock",
                scope="e2e",
                execution_status="ok",
                final_action="retrieve_draft",
                total_elapsed_ms=800.0,
                stage_elapsed_ms={"classify_ms": 40.0, "llm_ms": 600.0, "retrieval_ms": 80.0},
            ),
            # Case 3: Clarify (no LLM call)
            CaseResult(
                case_id="c3",
                repetition=1,
                profile="mock",
                scope="e2e",
                execution_status="ok",
                final_action="clarify",
                total_elapsed_ms=150.0,
                stage_elapsed_ms={"classify_ms": 40.0, "route_ms": 10.0},
            ),
            # Case 4: Escalate (no LLM call)
            CaseResult(
                case_id="c4",
                repetition=1,
                profile="mock",
                scope="e2e",
                execution_status="ok",
                final_action="escalate",
                total_elapsed_ms=120.0,
                stage_elapsed_ms={"classify_ms": 30.0, "route_ms": 10.0},
            ),
            # Case 5: Timeout error
            CaseResult(
                case_id="c5",
                repetition=1,
                profile="mock",
                scope="e2e",
                execution_status="timeout",
                error_code="deadline_exceeded",
                total_elapsed_ms=3000.0,
            ),
        ]

        summary = summarize_http_results(results)

        assert summary["total_requests"] == 5
        assert summary["ok_requests"] == 4
        assert summary["timeout_requests"] == 1
        assert summary["draft_count"] == 2
        assert summary["llm_branch_count"] == 2
        assert summary["no_llm_branch_count"] == 2
        assert summary["p95_total_seconds"] is not None
        assert summary["llm_branch_p95_seconds"] is not None
        assert summary["no_llm_branch_p95_seconds"] is not None
