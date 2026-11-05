"""Integration tests for native SQLite deadline probe, process isolation, and fault recovery (Task 2)."""

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.schemas import RoutingContext, IntentPrediction
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_performance import BudgetLedger
from pipeline.evaluation.system_server import ManagedDemoServer
from pipeline.preparation.utils import compute_sha256


@pytest.fixture
def test_inputs(tmp_path):
    kb_file = tmp_path / "approved_kb.v1.json"
    kb_data = [
        {
            "doc_id": "KB-RET-01",
            "document_id": "KB-RET-01",
            "version": "1.0",
            "status": "approved",
            "title": "Return Policy",
            "content": "Return items within 30 days of delivery.",
            "allowed_roles": ["agent", "customer"],
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_to": "2026-12-31T23:59:59Z",
        }
    ]
    kb_file.write_text(json.dumps(kb_data), encoding="utf-8")

    suite_manifest = tmp_path / "suite.manifest.json"
    manifest_data = {
        "status": "approved",
        "as_of": "2026-06-01T00:00:00Z",
        "files": {
            "cases": {"path": "cases.jsonl", "sha256": "dummy"},
            "kb": {"path": "approved_kb.v1.json", "sha256": compute_sha256(kb_file)},
        },
    }
    suite_manifest.write_text(json.dumps(manifest_data), encoding="utf-8")

    cases = [
        SystemCase(
            id="case-probe-01",
            primary_slice="supported",
            text="What is your return policy?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="demo-customer"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                answerable=True,
                gold_sources=[{"doc_id": "KB-RET-01", "version": "1.0"}],
            ),
        )
    ]

    return VerifiedSystemInputs(
        cases=cases,
        config=SystemConfig(),
        source_paths={"suite_manifest": suite_manifest, "kb": kb_file},
        input_hashes={"suite_manifest": compute_sha256(suite_manifest), "kb": compute_sha256(kb_file)},
        as_of=datetime(2026, 6, 1, tzinfo=timezone.utc),
        coverage={},
        manifest=manifest_data,
    )


class TestNativeSQLiteDeadlineProbe:
    def test_locked_db_causes_timeout_worker_terminated_and_no_late_records(self, test_inputs, tmp_path):
        """Native SQLite probe:
        1. Lock SQLite database externally with BEGIN EXCLUSIVE.
        2. Worker blocks on lock; request times out at deadline.
        3. Worker process is killed (terminate/join).
        4. Unlock DB; verify 0 late records exist.
        5. Worker process is restarted with handshake; retry succeeds without duplicate enqueue.
        """
        runtime_dir = tmp_path / "runtime_sqlite_probe"
        runtime_dir.mkdir()
        ledger_path = runtime_dir / "budget.sqlite3"
        server = ManagedDemoServer(run_nonce="nonce-probe-1", input_fingerprint="fp-probe-1")

        try:
            base_url = server.start(
                inputs=test_inputs,
                runtime_dir=runtime_dir,
                ledger_path=ledger_path,
                profile="mock",
            )
            assert server.is_running()

            demo_db = runtime_dir / "demo.sqlite3"
            orch_db = runtime_dir / "orchestration.sqlite3"

            # 1. Lock orchestration SQLite DB externally with an exclusive transaction
            lock_conn = sqlite3.connect(str(orch_db), timeout=0.1)
            lock_conn.execute("BEGIN EXCLUSIVE")

            submission_id = "sub-probe-timeout-001"
            payload = {
                "submission_id": submission_id,
                "profile_id": "demo-customer",
                "text": "What is your return policy?",
                "is_personal_lookup": False,
                "order_id": None,
            }

            # 2. Worker request times out because SQLite is locked
            timed_out = False
            try:
                with httpx.Client(base_url=base_url, timeout=0.30) as client:
                    client.post("/api/demo/runs", json=payload)
            except (httpx.TimeoutException, httpx.RequestError):
                timed_out = True

            assert timed_out, "Request should have timed out due to locked SQLite database!"

            # 3. Kill the worker process immediately
            server.close()
            assert not server.is_running(), "Worker process was not killed after deadline!"

            # 4. Release external lock and wait to prove no late writes occur
            lock_conn.rollback()
            lock_conn.close()
            time.sleep(0.15)

            # Check that timed-out submission has ZERO committed records
            with sqlite3.connect(str(orch_db)) as conn:
                conn.row_factory = sqlite3.Row
                c_runs = conn.execute("SELECT count(*) as cnt FROM runs WHERE run_id = ?", (submission_id,)).fetchone()
                assert c_runs["cnt"] == 0, "A late record was committed to runs after deadline!"

                c_esc = conn.execute("SELECT count(*) as cnt FROM escalation_queue WHERE run_id = ?", (submission_id,)).fetchone()
                assert c_esc["cnt"] == 0, "A late record was enqueued to escalation_queue after deadline!"

            # 5. Restart worker process with preserved DB and handshake
            restarted_url = server.restart()
            assert server.is_running()
            assert restarted_url.startswith("http://127.0.0.1:")

            # 6. Retry submission: now succeeds without duplicate enqueue
            with httpx.Client(base_url=restarted_url, timeout=5.0) as client:
                res = client.post("/api/demo/runs", json=payload)
                assert res.status_code == 200
                res_json = res.json()
                assert res_json.get("action") in ("retrieve_draft", "clarify", "escalate")

            with sqlite3.connect(str(orch_db)) as conn:
                conn.row_factory = sqlite3.Row
                c_runs = conn.execute("SELECT count(*) as cnt FROM runs WHERE run_id = ?", (submission_id,)).fetchone()
                assert c_runs["cnt"] == 1, "Expected exactly 1 run record after successful retry!"

        finally:
            server.close()

    def test_budget_ledger_preserves_reservations_across_worker_restarts(self, tmp_path):
        """Worker crash or termination preserves budget ledger reservations and counts without reset."""
        budget_db = tmp_path / "budget_probe.sqlite3"
        config = SystemConfig(max_llm_calls=5, max_estimated_cost_usd=1.0)
        ledger = BudgetLedger(db_path=budget_db, config=config)

        # Make 2 reservations
        r1 = ledger.reserve(100, 50)
        r2 = ledger.reserve(200, 100)
        ledger.record(r1, {"input_tokens": 80, "output_tokens": 40})
        # r2 remains unrecorded (simulating worker killed during LLM call)

        usage_before = ledger.summary()
        assert usage_before["reserved_calls"] == 2
        assert usage_before["completed_calls"] == 1
        assert usage_before["has_unknown_cost"] is True

        # Reopen ledger (simulating server restart with preserved DB)
        reopened_ledger = BudgetLedger(db_path=budget_db, config=config)
        usage_after = reopened_ledger.summary()

        assert usage_after["reserved_calls"] == 2
        assert usage_after["completed_calls"] == 1
        assert usage_after["has_unknown_cost"] is True
        assert usage_after["remaining_calls"] == 3


class TestRealDependencyFaultInjection:
    def test_real_pipeline_runner_handles_injected_dependency_faults(self, tmp_path):
        """PipelineRunner handles dependency failures via safe fallback and reason codes without unhandled crashes."""
        store = PersistentStore(db_path=str(tmp_path / "orch_faults.sqlite3"))

        # 1. Faulty intent client (timeout / connection error)
        class FailingIntentClient:
            def classify_intent(self, text, request_id=None):
                return IntentPrediction(
                    intent="unknown",
                    confidence=0.0,
                    margin=0.0,
                    model_version="fault",
                    error="ml_connection_timeout",
                )

        runner = PipelineRunner(intent_client=FailingIntentClient(), store=store)
        ctx = RoutingContext(ticket_customer_id="cust-fault-test")
        res = runner.run(text="Can I get a refund?", context=ctx, run_id="run-ml-fault")

        assert res["action"] == "manual_fallback"
        assert "ml_unavailable" in res["reason_codes"]
        assert res["requested_team"] == "general_support"
        assert res["draft_body"] is None
