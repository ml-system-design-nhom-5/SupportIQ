"""Integration tests for ManagedDemoServer loopback process lifecycle and handshake."""

import pytest
import httpx
from pathlib import Path
from datetime import datetime, timezone

from pipeline.evaluation import EvaluationError
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_server import ManagedDemoServer


@pytest.fixture
def sample_inputs(tmp_path):
    cases = [
        SystemCase(
            id="c1",
            primary_slice="supported",
            text="Query",
            true_intent="track_order",
            context=SystemCaseContext(ticket_customer_id="cust-1"),
            expected=SystemCaseExpected(actions=["retrieve_draft"]),
        )
    ]
    return VerifiedSystemInputs(
        cases=cases,
        config=SystemConfig(),
        source_paths={},
        input_hashes={},
        as_of=datetime.now(timezone.utc),
        coverage={},
        manifest={"status": "approved"},
    )


class TestManagedDemoServer:
    def test_quality_case_runs_inside_the_managed_worker(self, sample_inputs, tmp_path):
        server = ManagedDemoServer()
        runtime = tmp_path/'quality-worker'
        runtime.mkdir()
        try:
            url = server.start(sample_inputs, runtime, runtime/'budget.sqlite3', profile='mock')
            payload = {'case':sample_inputs.cases[0].model_dump(),'attempt_id':'inside-worker'}
            with httpx.Client(trust_env=False) as client:
                denied = client.post(url+'/api/evaluation/case',json=payload)
                assert denied.status_code==403
                response=client.post(url+'/api/evaluation/case',json=payload,
                    headers={'X-Evaluation-Nonce':server.run_nonce},timeout=5)
                assert response.status_code==200
                assert response.json()['case_id']=='c1'
                assert response.json()['execution_status']=='ok'
        finally:
            server.close()

    def test_server_lifecycle_and_handshake(self, sample_inputs, tmp_path):
        """ManagedDemoServer starts on loopback port, handshakes nonce, and closes cleanly."""
        runtime_dir = tmp_path / "runtime_server"
        runtime_dir.mkdir()
        ledger_path = runtime_dir / "budget.sqlite3"

        server = ManagedDemoServer()
        try:
            base_url = server.start(
                inputs=sample_inputs,
                runtime_dir=runtime_dir,
                ledger_path=ledger_path,
            )
            assert base_url.startswith("http://127.0.0.1:")
            assert server.is_running()

            # Handshake check: health endpoint responds
            health = server.check_health()
            assert health["status"] == "ok"

            # Restart preserves runtime directory and resumes cleanly
            restarted_url = server.restart()
            assert restarted_url.startswith("http://127.0.0.1:")
            assert server.is_running()
        finally:
            server.close()

        assert not server.is_running()
        # Ensure SQLite DB is unlocked and can be removed cleanly
        db_file = runtime_dir / "demo.sqlite3"
        if db_file.exists():
            db_file.unlink()

    def test_unauthorized_server_rejects_handshake(self, sample_inputs, tmp_path):
        """If server does not match run nonce / fingerprint, handshake raises EvaluationError."""
        runtime_dir = tmp_path / "runtime_fake"
        runtime_dir.mkdir()
        ledger_path = runtime_dir / "budget.sqlite3"

        server = ManagedDemoServer(run_nonce="run-nonce-12345")
        try:
            with pytest.raises(EvaluationError, match="handshake|nonce|fingerprint"):
                # Force invalid expected handshake
                server._verify_handshake(health_response={"status": "ok", "nonce": "wrong-nonce"})
        finally:
            server.close()
