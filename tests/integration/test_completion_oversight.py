"""Integration tests for 5 human oversight scenarios, SQLite audit trails, and tamper detection (Task 7)."""

import json
import sqlite3
import pytest
from pathlib import Path

from apps.core_backend.orchestration.store import PersistentStore
from apps.demo.app import create_app
from pipeline.evaluation.assess_system import evaluate_oversight
from pipeline.evaluation.system_contracts import CaseResult, SystemConfig, VerifiedSystemInputs
from pipeline.evaluation.system_execution import build_system_dependencies, run_oversight_scenarios


@pytest.fixture
def mock_inputs(tmp_path):
    kb_file = tmp_path / "approved_kb.v1.json"
    kb_data = [{
        "doc_id": "KB-01",
        "document_id": "KB-01",
        "version": "1.0",
        "status": "approved",
        "approved_by": "lead",
        "approved_at": "2026-01-01T00:00:00Z",
        "valid_from": "2026-01-01T00:00:00Z",
        "allowed_roles": ["agent", "customer"],
        "supported_intents": ["return_policy"],
        "answer_capabilities": ["return_conditions"],
        "title": "Return Policy",
        "content": "Return within 30 days.",
    }]
    kb_file.write_text(json.dumps(kb_data), encoding="utf-8")

    from datetime import datetime, timezone
    return VerifiedSystemInputs(
        cases=[],
        config=SystemConfig(),
        source_paths={"kb": kb_file},
        input_hashes={},
        as_of=datetime(2026, 6, 1, tzinfo=timezone.utc),
        coverage={},
        manifest={"status": "approved"},
    )


class TestHumanOversightAuditTrails:
    def test_five_oversight_scenarios_execute_and_verify_sqlite_audit(self, mock_inputs, tmp_path):
        """run_oversight_scenarios executes 5 scenarios (approve, edit, reject, escalate, tamper_detection)
        and evaluate_oversight verifies persistence in demo_feedback and escalation_queue.
        """
        runtime_dir = tmp_path / "runtime_oversight_5"
        runtime_dir.mkdir()
        deps = build_system_dependencies(mock_inputs, profile="mock", runtime_dir=runtime_dir, start_server=False)

        try:
            results = run_oversight_scenarios(deps, runtime_dir=runtime_dir)

            # Must contain 5 scenarios
            case_ids = {r.case_id for r in results}
            assert "oversight-approve" in case_ids or "oversight-feedback-audit" in case_ids
            assert "oversight-edit" in case_ids
            assert "oversight-reject" in case_ids
            assert "oversight-escalate" in case_ids
            assert "oversight-tamper-detection" in case_ids or "oversight-stale-hash" in case_ids

            demo_db = runtime_dir / "demo.sqlite3"
            oversight_eval = evaluate_oversight(results, db_path=demo_db)

            assert oversight_eval["status"] == "pass"
            assert oversight_eval["oversight_gate_passed"] is True
            assert oversight_eval["audit_pass_count"] >= 5

        finally:
            deps.close()

    def test_missing_draft_409_is_not_counted_as_tamper_security_pass(self, tmp_path):
        """A run that never created a draft returning 409 must NOT be counted as tamper detection pass."""
        demo_db = tmp_path / "empty_demo.sqlite3"
        results = [
            CaseResult(
                case_id="oversight-tamper-detection",
                repetition=1,
                profile="mock",
                scope="oversight",
                execution_status="ok",
                audit_evidence={"missing_draft": True, "http_status": 409},
            )
        ]
        res = evaluate_oversight(results, db_path=demo_db)
        assert res["status"] == "fail"
        assert res["oversight_gate_passed"] is False
