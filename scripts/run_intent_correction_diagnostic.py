"""Bounded, explicitly oracle-assisted diagnostic through the real staff API.

Keeps initial outcomes separate from intervention outcomes. It does not measure
automatic classifier accuracy or pretend that staff time is human study data.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from apps.backend.main import create_app
from apps.backend.platform.config import Settings
from apps.backend.platform.database import Database
from apps.backend.platform.models import AuditEntry
from apps.backend.seed import seed
from scripts.collect_final_acceptance_evidence import (
    AcceptanceEvidenceCollector,
    EphemeralMockAIGateway,
    resolve_database_url,
)
from scripts.native_runtime import configure_runtime_environment

DEFAULT_DIAGNOSTIC_CASES = [
    "final-case-03",
    "final-case-04",
    "final-case-05",
    "final-case-06",
    "final-case-07",
    "final-case-10",
    "final-case-12",
]

VALID_ANALYSIS_TERMINAL = {"ready", "unavailable"}
VALID_DRAFT_TERMINAL = {
    "draft_ready",
    "abstained",
    "escalation_recommended",
    "unavailable",
    "llm_unavailable",
}


def sanitize_error(err: Exception | str) -> str:
    """Best-effort credential scrubbing (database URIs, passwords, bearer tokens).

    NOTE: This does not claim universal PII scrubbing for arbitrary exception text.
    """
    msg = str(err)
    msg = re.sub(r"://([^:@\s]+):([^@\s]+)@", r"://\1:***@", msg)
    msg = re.sub(r"password=([^\s;]+)", r"password=***", msg, flags=re.I)
    msg = re.sub(r"bearer\s+[a-zA-Z0-9_\-\.]+", r"Bearer ***", msg, flags=re.I)
    msg = re.sub(r"token=([^\s&]+)", r"token=***", msg, flags=re.I)
    return msg


def terminal(client: TestClient, ticket_id: str, timeout: float = 25.0) -> Dict[str, Any]:
    """Poll console ticket view until suggestion reaches an explicit non-pending terminal state."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/v1/console/tickets/{ticket_id}")
        response.raise_for_status()
        view = response.json()
        suggestion = view.get("suggestion")
        if isinstance(suggestion, dict):
            a_status = suggestion.get("analysis_status")
            d_status = suggestion.get("draft_status")
            # Strictly require explicit valid terminal states, never accept missing or None fields
            if a_status in VALID_ANALYSIS_TERMINAL and d_status in VALID_DRAFT_TERMINAL:
                return view
        time.sleep(0.05)
    raise TimeoutError(
        f"Suggestion for ticket {ticket_id} did not reach explicit terminal state within {timeout}s budget"
    )


def run_intent_correction_diagnostic(
    selected_cases: Optional[List[str]] = None,
    mode: str = "live",
    ai_service_base_url: Optional[str] = None,
    mock_gateway: Optional[EphemeralMockAIGateway] = None,
    output_dir: Optional[Path | str] = None,
    secrets_path: Optional[str] = None,
    poll_timeout: float = 25.0,
    max_cases: int = 12,
) -> Dict[str, Any]:
    """Execute bounded, oracle-assisted staff intent correction diagnostic.

    Args:
        selected_cases: Case IDs to evaluate (defaults to 7 low-confidence abstention cases).
        mode: Execution mode ('live' or 'mock').
        ai_service_base_url: Base URL of AI gateway. Permitted only in live mode.
        mock_gateway: Optional in-process EphemeralMockAIGateway instance for mock mode.
        output_dir: Exclusive directory where artifacts are stored. Fails if non-empty.
        secrets_path: Path to local application credentials or None for default resolution.
        poll_timeout: Maximum seconds to poll per suggestion before raising TimeoutError.
        max_cases: Bounded case count loaded from suite (must cover all selected cases).

    Returns:
        Structured result dictionary with run_id, output_dir, created_schema, records, and summary.
    """
    configure_runtime_environment()

    # Pre-execution validation before network/database operations
    if mode not in ("live", "mock"):
        raise ValueError(f"Unknown mode '{mode}'. Mode must be 'live' or 'mock'.")

    if mode == "mock":
        if ai_service_base_url is not None:
            raise ValueError(
                f"Mock mode rejects arbitrary ai_service_base_url ('{ai_service_base_url}'). "
                "Only runner-owned EphemeralMockAIGateway or explicit mock_gateway instance is permitted."
            )
        if mock_gateway is not None and not isinstance(mock_gateway, EphemeralMockAIGateway):
            raise TypeError("mock_gateway must be an instance of EphemeralMockAIGateway")
    else:
        if mock_gateway is not None:
            raise ValueError("mock_gateway instance cannot be provided in live mode.")

    active_mock_gateway: Optional[EphemeralMockAIGateway] = None
    owns_mock_gateway: bool = False
    owner = None
    application = None
    schema_created = False
    teardown_error: Optional[str] = None
    schema = "diag_intent_" + uuid.uuid4().hex[:10]
    out: Optional[Path] = None
    records: List[Dict[str, Any]] = []

    try:
        if mode == "mock":
            if mock_gateway is not None:
                active_mock_gateway = mock_gateway
                owns_mock_gateway = False
            else:
                active_mock_gateway = EphemeralMockAIGateway(mode="normal")
                active_mock_gateway.start()
                owns_mock_gateway = True
            effective_ai_url = active_mock_gateway.base_url
        else:
            effective_ai_url = ai_service_base_url or "http://127.0.0.1:8002"

        effective_secrets = secrets_path or str(ROOT / ".local/application.json")
        collector = AcceptanceEvidenceCollector(
            mode=mode,
            max_cases=max_cases,
            secrets_path=effective_secrets,
            live_ai_url=effective_ai_url,
        )

        # Validate case selection strictly: reject partial selection
        suite_cases_by_id = {c["id"]: c for c in collector.cases}
        case_ids = list(selected_cases) if selected_cases else list(DEFAULT_DIAGNOSTIC_CASES)
        missing_ids = [cid for cid in case_ids if cid not in suite_cases_by_id]
        if missing_ids:
            raise ValueError(
                f"Selected case IDs {missing_ids} not found in available suite ({len(collector.cases)} cases)! "
                "Partial selection is rejected."
            )
        cases = [suite_cases_by_id[cid] for cid in case_ids]

        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
        if output_dir:
            out = Path(output_dir)
            if out.exists() and any(out.iterdir()):
                raise FileExistsError(
                    f"Output directory '{out}' already exists and is non-empty. "
                    "Exclusive artifact directory required to prevent overwriting evidence."
                )
            out.mkdir(parents=True, exist_ok=True)
        else:
            out = ROOT / "artifacts/evaluation" / ("coordinator-intent-correction-" + run_id)
            out.mkdir(parents=True, exist_ok=False)

        owner_url, default_passwords = resolve_database_url(effective_secrets)
        owner = create_engine(owner_url, hide_parameters=True)

        with owner.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        application = create_engine(
            owner_url,
            connect_args={"options": f"-csearch_path={schema}"},
            hide_parameters=True,
        )
        db = Database(application)
        db.create_schema()

        passwords = {
            role: default_passwords.get(role, uuid.uuid4().hex)
            for role in ("customer", "staff", "manager", "admin")
        }
        seed(db, passwords)

        settings = Settings(
            database_url_app=owner_url,
            database_url_owner=owner_url,
            session_cookie_secure=False,
            allowed_origins=["http://testserver"],
            ai_service_base_url=effective_ai_url,
            ai_service_analysis_timeout_ms=3000,
            ai_service_draft_timeout_ms=11000,
            job_poll_interval_ms=50,
        )

        app = create_app(settings=settings, database=db, start_worker=True)
        staff_app = create_app(settings=settings, database=db, start_worker=False)

        with TestClient(app) as customer, TestClient(staff_app) as staff:
            for client, role in ((customer, "customer"), (staff, "staff")):
                client.headers["Origin"] = "http://testserver"
                auth = client.post("/v1/sessions", json={"login_name": f"{role}-1", "password": passwords[role]})
                auth.raise_for_status()
                if role == "staff":
                    staff_account_id = auth.json().get("account_id")

            for case in cases:
                record: Dict[str, Any] = {
                    "case_id": case["id"],
                    "query": case["query"],
                    "gold_intent": case["intent"],
                    "intervention_authority": "coordinator_AI_delegated_stakeholder",
                    "intervention_type": "oracle_intent_correction_diagnostic",
                    "initial": None,
                    "assisted": None,
                }
                try:
                    started = time.perf_counter()
                    payload = {
                        "message": case["query"],
                        **({"order_id": case["order_id"]} if case.get("order_id") else {}),
                    }
                    submitted = customer.post(
                        "/v1/shop/tickets",
                        json=payload,
                        headers={"Idempotency-Key": uuid.uuid4().hex},
                    )
                    submitted.raise_for_status()
                    ticket_id = submitted.json()["ticket_id"]
                    record["ticket_id"] = ticket_id
                    record["initial"] = terminal(staff, ticket_id, timeout=poll_timeout)
                    record["initial_system_seconds"] = round(time.perf_counter() - started, 4)

                    initial_sug = record["initial"].get("suggestion") or {}
                    correction = initial_sug.get("draft_status") == "abstained"
                    record["correction_executed"] = correction

                    if correction:
                        record["correction_started_at"] = datetime.now(timezone.utc).isoformat()
                        started_corr = time.perf_counter()
                        changed = staff.post(
                            f"/v1/console/tickets/{ticket_id}/suggestions",
                            json={"intent_override": case["intent"]},
                            headers={"Idempotency-Key": uuid.uuid4().hex},
                        )
                        record["correction_http_status"] = changed.status_code
                        changed.raise_for_status()
                        record["assisted"] = terminal(staff, ticket_id, timeout=poll_timeout)
                        record["correction_system_seconds"] = round(time.perf_counter() - started_corr, 4)
                        record["correction_completed_at"] = datetime.now(timezone.utc).isoformat()

                    response = customer.get(f"/v1/shop/tickets/{ticket_id}")
                    response.raise_for_status()
                    customer_view = response.json()
                    record["customer_no_auto_send"] = (
                        "reply" in customer_view
                        and customer_view["reply"] is None
                        and customer_view.get("customer_status") == "received"
                    )

                    with db.transaction() as session:
                        entries = session.scalars(
                            select(AuditEntry).where(
                                AuditEntry.ticket_id == ticket_id,
                                AuditEntry.event_type == "intent.overridden",
                            )
                        ).all()
                        matching_audit = []
                        for e in entries:
                            chosen = (e.data or {}).get("chosen_intent") if isinstance(e.data, dict) else None
                            is_intent_match = (chosen == case["intent"])
                            is_actor_match = (e.actor_account_id == staff_account_id)
                            matching_audit.append({
                                "event_type": e.event_type,
                                "actor_account_id": e.actor_account_id,
                                "data": e.data,
                                "occurred_at": e.occurred_at.isoformat() if hasattr(e.occurred_at, "isoformat") else str(e.occurred_at),
                                "chosen_intent_matches": is_intent_match,
                                "actor_matches": is_actor_match,
                            })
                        record["override_audit"] = matching_audit

                    if correction:
                        exact_match = any(
                            a["chosen_intent_matches"] and a["actor_matches"]
                            for a in record["override_audit"]
                        )
                        assert exact_match, (
                            f"Correction audit missing exact actor '{staff_account_id}' or chosen intent '{case['intent']}'!"
                        )
                except Exception as error:
                    err_cls = type(error).__name__
                    record["error_type"] = err_cls
                    if isinstance(error, TimeoutError):
                        record["error_category"] = "timeout"
                    elif "HTTP" in err_cls or "Request" in err_cls:
                        record["error_category"] = "network_or_http_error"
                    else:
                        record["error_category"] = "redacted_error"
                    record["error_detail"] = sanitize_error(error)

                records.append(record)
                if out:
                    (out / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    finally:
        if application is not None:
            try:
                application.dispose()
            except Exception as e:
                msg = f"Application engine disposal failed: {sanitize_error(e)}"
                teardown_error = (teardown_error + "; " + msg) if teardown_error else msg
        if schema_created and owner is not None:
            try:
                with owner.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            except Exception as drop_err:
                msg = f"Failed to drop schema {schema}: {sanitize_error(drop_err)}"
                sys.stderr.write(f"Warning: {msg}\n")
                teardown_error = (teardown_error + "; " + msg) if teardown_error else msg
        if owner is not None:
            try:
                owner.dispose()
            except Exception as e:
                msg = f"Owner engine disposal failed: {sanitize_error(e)}"
                teardown_error = (teardown_error + "; " + msg) if teardown_error else msg
        if owns_mock_gateway and active_mock_gateway is not None:
            try:
                active_mock_gateway.stop()
            except Exception:
                pass

    kb_bytes = (ROOT / "data/knowledge/approved_kb.v2.json").read_bytes()
    manifest_data = {
        "run_id": run_id,
        "mode": mode,
        "cases_sha256": collector.manifest_cases_sha256,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "sample_count": len(records),
        "purpose": "Actual staff API correction diagnostic, not automatic classifier accuracy or measured human productivity.",
        "boundary": (
            "TestClient HTTP application, real isolated PostgreSQL worker, actual ML/BGE/Gemini gateway."
            if mode == "live"
            else "TestClient HTTP application, real isolated PostgreSQL worker, ephemeral loopback mock AI gateway."
        ),
        "source_snapshot": "data/knowledge/approved_kb.v2.json",
        "source_sha256": hashlib.sha256(kb_bytes).hexdigest(),
        "no_reply_send_requested": True,
        "teardown_success": teardown_error is None,
        "teardown_error": teardown_error,
    }
    if out:
        (out / "manifest.json").write_text(json.dumps(manifest_data, indent=2), encoding="utf-8")

    summary_data = {
        "run_id": run_id,
        "mode": mode,
        "cases": len(records),
        "corrected": sum(r.get("correction_executed", False) for r in records),
        "assisted_drafts": sum(
            (r.get("assisted") or {}).get("suggestion", {}).get("draft_status") == "draft_ready"
            for r in records
        ),
        "errors": sum("error_type" in r for r in records),
        "no_auto_send_all": all(r.get("customer_no_auto_send", False) for r in records),
        "teardown_success": teardown_error is None,
        "teardown_error": teardown_error,
    }
    if out:
        (out / "summary.json").write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    return {
        "run_id": run_id,
        "output_dir": str(out) if out else "",
        "created_schema": schema,
        "manifest": manifest_data,
        "summary": summary_data,
        "records": records,
    }


def main():
    parser = argparse.ArgumentParser(description="Run bounded oracle-assisted staff intent correction diagnostic.")
    parser.add_argument("--mode", default="live", choices=["live", "mock"], help="Execution mode")
    parser.add_argument("--ai-url", default=None, help="AI service base URL")
    parser.add_argument("--cases", default=None, help="Comma-separated case IDs to run")
    parser.add_argument("--output-dir", default=None, help="Explicit output directory")
    parser.add_argument("--poll-timeout", type=float, default=25.0, help="Per-suggestion poll timeout seconds")
    parser.add_argument("--secrets-path", default=None, help="Path to application secrets file")
    args = parser.parse_args()

    selected = [c.strip() for c in args.cases.split(",")] if args.cases else None
    res = run_intent_correction_diagnostic(
        selected_cases=selected,
        mode=args.mode,
        ai_service_base_url=args.ai_url,
        output_dir=args.output_dir,
        secrets_path=args.secrets_path,
        poll_timeout=args.poll_timeout,
    )
    out_dir_path = Path(res["output_dir"]).resolve() if res.get("output_dir") else ROOT
    try:
        print(out_dir_path.relative_to(ROOT))
    except ValueError:
        print(out_dir_path)
    print(json.dumps(res["summary"]))

    summary = res["summary"]
    if not summary.get("teardown_success", True) or not summary.get("no_auto_send_all", True):
        sys.exit(1)


if __name__ == "__main__":
    main()
