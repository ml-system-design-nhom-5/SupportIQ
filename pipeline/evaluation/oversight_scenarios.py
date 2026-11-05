"""Execution of human oversight, session ownership, and persistence scenarios."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import TYPE_CHECKING, List

from pipeline.evaluation.system_contracts import CaseResult

if TYPE_CHECKING:
    from pipeline.evaluation.system_execution import SystemDependencies


def run_oversight_scenarios(
    deps: SystemDependencies,
    runtime_dir: Path | str,
) -> List[CaseResult]:
    """Execute human oversight, session ownership, and idempotency scenarios against demo app.
    Collects actual database persistence facts and returns structured CaseResult records.
    """
    from fastapi.testclient import TestClient

    r_dir = Path(runtime_dir).resolve()
    results: List[CaseResult] = []

    client_a = TestClient(deps.demo_app, cookies={"demo_session_id": "eval-session-A"})
    client_b = TestClient(deps.demo_app, cookies={"demo_session_id": "eval-session-B"})

    # 1. Submit a base run as Session A
    sub_id = "eval-over-sub-001"
    resp_sub = client_a.post("/api/demo/runs", json={
        "submission_id": sub_id,
        "profile_id": "demo-customer",
        "text": "What is the return policy?",
        "is_personal_lookup": False,
    })
    run_data = resp_sub.json() if resp_sub.status_code == 200 else {}
    run_id = run_data.get("run_id") or sub_id
    has_draft = bool(run_data.get("draft_body"))
    current_hash = run_data.get("draft_hash") or ""

    # Scenario 1: Session B cross-session feedback rejection
    t0 = time.perf_counter()
    resp_cross = client_b.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "approve",
        "draft_hash": current_hash or "initial-hash",
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    cross_rejected = (resp_cross.status_code in (403, 409)) and has_draft

    results.append(CaseResult(
        case_id="oversight-session-ownership",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if cross_rejected else "error",
        error_code=None if cross_rejected else ("missing_draft" if not has_draft else f"status_{resp_cross.status_code}"),
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "session_owner": "eval-session-A",
            "attacker_session": "eval-session-B",
            "http_status": resp_cross.status_code,
            "missing_draft": not has_draft,
            "ownership_protected": cross_rejected,
        },
    ))

    # Scenario 2: Stale draft hash approval rejection (409)
    t0 = time.perf_counter()
    resp_stale = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "approve",
        "draft_hash": "stale-tampered-hash-000",
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    stale_rejected = (resp_stale.status_code in (400, 409)) and has_draft

    results.append(CaseResult(
        case_id="oversight-stale-hash",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if stale_rejected else "error",
        error_code=None if stale_rejected else ("missing_draft" if not has_draft else f"status_{resp_stale.status_code}"),
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "expected_hash": current_hash,
            "submitted_hash": "stale-tampered-hash-000",
            "http_status": resp_stale.status_code,
            "missing_draft": not has_draft,
            "stale_protection_passed": stale_rejected,
        },
    ))

    # Scenario 3: Feedback audit verification (Approve) & transaction safety
    t0 = time.perf_counter()
    resp_approve = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "approve",
        "draft_hash": current_hash,
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    demo_db = r_dir / "demo.sqlite3"
    feedback_count = 0
    tx_blocked = True
    if demo_db.exists():
        with sqlite3.connect(demo_db) as conn:
            conn.row_factory = sqlite3.Row
            fb_row = conn.execute("SELECT COUNT(*) as cnt FROM demo_feedback WHERE run_id = ?", (run_id,)).fetchone()
            feedback_count = fb_row["cnt"] if fb_row else 0
            sub_row = conn.execute("SELECT result_json FROM demo_submissions WHERE run_id = ?", (run_id,)).fetchone()
            if sub_row:
                sub_data = json.loads(sub_row["result_json"])
                tx_blocked = (sub_data.get("can_execute_transaction") is False)

    results.append(CaseResult(
        case_id="oversight-approve",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if (resp_approve.status_code == 200 and tx_blocked) else "error",
        error_code=None if (resp_approve.status_code == 200 and tx_blocked) else "approve_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "feedback_recorded": feedback_count >= 1,
            "can_execute_transaction": not tx_blocked,
            "audit_verified": (resp_approve.status_code == 200 and tx_blocked),
        },
    ))

    # Scenario 4: Edit draft with human reviewer edited text and revised hash
    t0 = time.perf_counter()
    resp_edit = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "edit",
        "draft_hash": current_hash,
        "edited_text": "Updated verified return policy: returns accepted within 30 days.",
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    new_hash = resp_edit.json().get("current_draft_hash") if resp_edit.status_code == 200 else None

    results.append(CaseResult(
        case_id="oversight-edit",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if (resp_edit.status_code == 200 and new_hash) else "error",
        error_code=None if (resp_edit.status_code == 200 and new_hash) else "edit_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": run_id,
            "original_hash": current_hash,
            "revised_hash": new_hash,
            "edit_verified": resp_edit.status_code == 200,
        },
    ))

    # Scenario 5: Reject draft
    t0 = time.perf_counter()
    resp_reject = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "reject",
        "draft_hash": new_hash or current_hash,
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    results.append(CaseResult(
        case_id="oversight-reject",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if resp_reject.status_code == 200 else "error",
        error_code=None if resp_reject.status_code == 200 else "reject_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={"run_id": run_id, "reject_verified": resp_reject.status_code == 200},
    ))

    # Scenario 6: Escalate draft feedback
    t0 = time.perf_counter()
    resp_esc = client_a.post(f"/api/demo/runs/{run_id}/feedback", json={
        "action": "escalate",
        "draft_hash": new_hash or current_hash,
    })
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    results.append(CaseResult(
        case_id="oversight-escalate",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if resp_esc.status_code == 200 else "error",
        error_code=None if resp_esc.status_code == 200 else "escalate_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={"run_id": run_id, "escalate_verified": resp_esc.status_code == 200},
    ))

    # Scenario 7: Concurrent idempotency on orchestration store
    t0 = time.perf_counter()
    idem_run_id = "eval-idem-test-999"
    saved1 = deps.store.save_run_and_escalate_atomic(
        run_id=idem_run_id,
        result={"run_id": idem_run_id, "action": "escalate"},
        escalate_info={"decision_id": "dec-1", "target_team": "support", "target_queue": "standard", "reason_codes": []},
    )
    saved2 = deps.store.save_run_and_escalate_atomic(
        run_id=idem_run_id,
        result={"run_id": idem_run_id, "action": "escalate"},
        escalate_info={"decision_id": "dec-1", "target_team": "support", "target_queue": "standard", "reason_codes": []},
    )
    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    idempotent_ok = (saved1 is True and saved2 is False)

    results.append(CaseResult(
        case_id="oversight-idempotent-persistence",
        repetition=1,
        profile=deps.profile,
        scope="oversight",
        execution_status="ok" if idempotent_ok else "error",
        error_code=None if idempotent_ok else "idempotency_failed",
        stage_elapsed_ms={"check_ms": elapsed_ms},
        total_elapsed_ms=elapsed_ms,
        audit_evidence={
            "run_id": idem_run_id,
            "first_save": saved1,
            "second_save": saved2,
            "idempotency_preserved": idempotent_ok,
        },
    ))

    return results
