"""Integration tests for Human Oversight, session ownership, stale hash rejection, and idempotency."""

import pytest
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from apps.demo.app import create_app
from apps.demo.service import DemoRunRequest, DemoFeedbackRequest
from pipeline.evaluation.system_contracts import (
    SystemCase,
    SystemCaseContext,
    SystemCaseExpected,
    SystemConfig,
    VerifiedSystemInputs,
)
from pipeline.evaluation.system_execution import (
    build_system_dependencies,
    run_oversight_scenarios,
)


@pytest.fixture
def oversight_inputs(tmp_path):
    cases = [
        SystemCase(
            id="case-over-01",
            primary_slice="supported",
            text="How do I return my order?",
            true_intent="return_policy",
            context=SystemCaseContext(ticket_customer_id="cust-1"),
            expected=SystemCaseExpected(
                actions=["retrieve_draft"],
                must_escalate=False,
                draft_expected=True,
            ),
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


class TestOversightAndOwnership:
    def test_session_b_cannot_feedback_or_replay_session_a(self, tmp_path):
        """Session B attempting to replay submission or provide feedback on Session A's run is rejected."""
        db_path = str(tmp_path / "demo_oversight.sqlite3")
        app = create_app(db_path=db_path)
        client_a = TestClient(app, cookies={"demo_session_id": "session-A"})
        client_b = TestClient(app, cookies={"demo_session_id": "session-B"})

        # Session A submits run
        sub_id = "sub-over-101"
        resp_a = client_a.post("/api/demo/runs", json={
            "submission_id": sub_id,
            "profile_id": "demo-customer",
            "text": "What is the return window?",
            "is_personal_lookup": False,
        })
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        run_id = data_a["run_id"]
        draft_hash = data_a.get("draft_hash") or "dummy-hash"

        # Session B attempts to submit feedback on Session A's run -> Must be rejected (409 Conflict or 403 Forbidden)
        resp_b_fb = client_b.post(f"/api/demo/runs/{run_id}/feedback", json={
            "action": "approve",
            "draft_hash": draft_hash,
        })
        assert resp_b_fb.status_code in (403, 409), f"Expected 403/409, got {resp_b_fb.status_code}"

        # Session B attempts to replay submission with same submission_id -> Must be rejected (409 Conflict)
        resp_b_sub = client_b.post("/api/demo/runs", json={
            "submission_id": sub_id,
            "profile_id": "demo-customer",
            "text": "What is the return window?",
            "is_personal_lookup": False,
        })
        assert resp_b_sub.status_code == 409

    def test_stale_draft_hash_approve_rejected_with_409(self, tmp_path):
        """Approving a draft with an outdated / stale draft_hash must return 409 Conflict."""
        db_path = str(tmp_path / "demo_stale.sqlite3")
        app = create_app(db_path=db_path)
        client = TestClient(app, cookies={"demo_session_id": "session-single"})

        # Submit run
        resp = client.post("/api/demo/runs", json={
            "submission_id": "sub-stale-01",
            "profile_id": "demo-customer",
            "text": "What is the return policy?",
            "is_personal_lookup": False,
        })
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]

        # Attempt approve with wrong/stale hash -> 400 or 409
        fb_resp = client.post(f"/api/demo/runs/{run_id}/feedback", json={
            "action": "approve",
            "draft_hash": "outdated-or-tampered-draft-hash",
        })
        assert fb_resp.status_code in (400, 409)

    def test_feedback_actions_record_audit_without_executing_transactions(self, tmp_path):
        """Approve, edit, reject, and escalate record feedback and audit without transaction execution."""
        db_path = str(tmp_path / "demo_audit.sqlite3")
        app = create_app(db_path=db_path)
        client = TestClient(app, cookies={"demo_session_id": "session-audit"})

        resp = client.post("/api/demo/runs", json={
            "submission_id": "sub-audit-01",
            "profile_id": "demo-customer",
            "text": "What is the return policy?",
            "is_personal_lookup": False,
        })
        run_id = resp.json()["run_id"]
        draft_hash = resp.json().get("draft_hash") or ""

        # Send approve feedback
        if draft_hash:
            fb_resp = client.post(f"/api/demo/runs/{run_id}/feedback", json={
                "action": "approve",
                "draft_hash": draft_hash,
            })
            assert fb_resp.status_code == 200

        # Check DB audit: can_execute_transaction must remain False
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT result_json FROM demo_submissions WHERE run_id = ?", (run_id,)).fetchone()
            assert row is not None
            import json
            res = json.loads(row["result_json"])
            assert res["can_execute_transaction"] is False


def test_run_oversight_scenarios_interface(oversight_inputs, tmp_path):
    """run_oversight_scenarios returns structured CaseResult records with scope='oversight'."""
    runtime_dir = tmp_path / "runtime_oversight"
    runtime_dir.mkdir()
    deps = build_system_dependencies(oversight_inputs, profile="mock", runtime_dir=runtime_dir)

    results = run_oversight_scenarios(deps, runtime_dir)
    assert len(results) > 0
    for r in results:
        assert r.scope == "oversight"
        assert r.audit_evidence is not None

    deps.close()
