"""Tests for bounded oracle-assisted staff intent correction diagnostic (Worker C).

Verifies:
- Initial abstention preserved distinctly from assisted outcomes.
- Real staff override API endpoint (POST /v1/console/tickets/{ticket_id}/suggestions)
  called with gold expected intent.
- Second terminal suggestion reaches draft_ready upon intent correction.
- Customer ticket verified with reply is None, customer_status == 'received' (no auto-send).
- Database audit entry persisted with event_type 'intent.overridden', actor account, and chosen intent.
- Mock mode strictly allows runner-owned EphemeralMockAIGateway, rejecting live/variant URLs.
- Selection rejects partial/unknown case IDs fail closed.
- Non-empty output directory rejected to ensure exclusive artifacts.
- Post-CREATE failure teardown drops exact created schema cleanly without product test hooks.
- Teardown error tracking records failure without claiming clean state.
- CLI execution exits with non-zero code on teardown or no-auto-send failure.
- Explicit terminal status checking (rejecting missing/None fields).
"""

import json
from pathlib import Path
import pytest
from sqlalchemy import create_engine, text

from scripts.collect_final_acceptance_evidence import (
    EphemeralMockAIGateway,
    resolve_database_url,
)
from scripts.run_intent_correction_diagnostic import (
    main,
    run_intent_correction_diagnostic,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mock_gateway():
    """Start an ephemeral mock AI gateway for testing."""
    gateway = EphemeralMockAIGateway(mode="normal")
    gateway.start()
    yield gateway
    gateway.stop()


def test_intent_correction_diagnostic_controlled_flow(tmp_path, mock_gateway, monkeypatch):
    """Proves: initial low-confidence abstention -> real staff override -> terminal draft_ready and persisted audit."""
    # Offline loopback mock gateway test explicitly opts out of spaCy NER when en_core_web_sm is absent.
    monkeypatch.setenv("SUPPORTIQ_REQUIRE_PRIVACY_NER", "false")
    # Configure mock gateway to simulate initial abstention for final-case-03
    mock_gateway.set_initial_abstain_cases({"final-case-03"})

    out_dir = tmp_path / "diag_test_run"
    res = run_intent_correction_diagnostic(
        selected_cases=["final-case-03"],
        mode="mock",
        mock_gateway=mock_gateway,
        output_dir=out_dir,
        poll_timeout=10.0,
        max_cases=12,
    )

    summary = res["summary"]
    assert summary["cases"] == 1
    assert summary["corrected"] == 1
    assert summary["assisted_drafts"] == 1
    assert summary["no_auto_send_all"] is True
    assert summary["errors"] == 0
    assert summary["teardown_success"] is True
    assert summary["teardown_error"] is None

    records = res["records"]
    assert len(records) == 1
    r = records[0]

    # 1. Initial baseline preserved
    assert r["case_id"] == "final-case-03"
    assert r["gold_intent"] == "refund_policy"
    assert r["initial"] is not None
    assert r["initial"]["suggestion"]["draft_status"] == "abstained"
    assert r["initial"]["suggestion"]["analysis_status"] == "ready"
    assert r["initial_system_seconds"] > 0

    # 2. Staff override executed through real console endpoint
    assert r["correction_executed"] is True
    assert r["correction_http_status"] == 202
    assert r["correction_started_at"] is not None
    assert r["correction_completed_at"] is not None
    assert r["correction_system_seconds"] > 0

    # 3. Assisted terminal result
    assert r["assisted"] is not None
    assert r["assisted"]["suggestion"]["draft_status"] == "draft_ready"
    assert r["assisted"]["suggestion"]["analysis_status"] == "ready"
    assert r["assisted"]["suggestion"]["intent_override"] == "refund_policy"

    # 4. Human oversight invariant: customer never received unapproved automated reply
    assert r["customer_no_auto_send"] is True

    # 5. Database audit entry persisted in PostgreSQL audit table with matching intent and actor
    assert len(r["override_audit"]) == 1
    audit = r["override_audit"][0]
    assert audit["event_type"] == "intent.overridden"
    assert audit["actor_account_id"] is not None
    assert audit["data"]["chosen_intent"] == "refund_policy"
    assert audit["chosen_intent_matches"] is True
    assert audit["actor_matches"] is True

    # 6. Honest oracle diagnostic labeling in record and manifest
    assert r["intervention_authority"] == "coordinator_AI_delegated_stakeholder"
    assert r["intervention_type"] == "oracle_intent_correction_diagnostic"

    manifest_file = out_dir / "manifest.json"
    assert manifest_file.exists()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    assert manifest["sample_count"] == 1
    assert manifest["mode"] == "mock"
    assert "ephemeral loopback mock AI gateway" in manifest["boundary"]
    assert manifest["no_reply_send_requested"] is True
    assert manifest["teardown_success"] is True

    # 7. Exact created schema is dropped in PostgreSQL
    created_schema = res["created_schema"]
    owner_url, _ = resolve_database_url()
    owner = create_engine(owner_url)
    with owner.connect() as conn:
        schema_exists = conn.execute(
            text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
            {"s": created_schema},
        ).scalar()
        assert schema_exists is None, f"Schema {created_schema} must be dropped after run!"
    owner.dispose()

    # Reset mock gateway
    mock_gateway.set_initial_abstain_cases(set())


@pytest.mark.parametrize(
    "bad_url",
    [
        "http://127.0.0.1:8002",
        "http://127.0.0.1:8002/",
        "http://localhost:8002",
        "http://localhost:8002/",
        "http://0.0.0.0:8002",
        "http://arbitrary-live-host:9000",
    ],
)
def test_intent_correction_diagnostic_rejects_mock_with_arbitrary_urls(bad_url):
    """Mock mode fails closed before network if configured with any URL variant."""
    with pytest.raises(ValueError, match="Mock mode rejects arbitrary ai_service_base_url"):
        run_intent_correction_diagnostic(
            selected_cases=["final-case-03"],
            mode="mock",
            ai_service_base_url=bad_url,
        )


def test_intent_correction_diagnostic_rejects_unknown_mode():
    """Diagnostic runner fails closed before network on unknown mode."""
    with pytest.raises(ValueError, match="Unknown mode 'invalid_mode'"):
        run_intent_correction_diagnostic(
            selected_cases=["final-case-03"],
            mode="invalid_mode",
        )


def test_intent_correction_diagnostic_rejects_invalid_mock_gateway_type():
    """Mock mode requires EphemeralMockAIGateway instance if provided."""
    with pytest.raises(TypeError, match="mock_gateway must be an instance of EphemeralMockAIGateway"):
        run_intent_correction_diagnostic(
            selected_cases=["final-case-03"],
            mode="mock",
            mock_gateway="not_an_instance",  # type: ignore
        )


def test_intent_correction_diagnostic_rejects_partial_selection(mock_gateway):
    """Selection fails closed when unknown or missing case IDs are passed."""
    with pytest.raises(ValueError, match="Partial selection is rejected"):
        run_intent_correction_diagnostic(
            selected_cases=["final-case-03", "unknown-case-id-999"],
            mode="mock",
            mock_gateway=mock_gateway,
        )


def test_intent_correction_diagnostic_rejects_non_empty_output_dir(tmp_path, mock_gateway):
    """Output directory must be exclusive; non-empty directory is rejected to protect artifacts."""
    occupied = tmp_path / "occupied_dir"
    occupied.mkdir(parents=True, exist_ok=True)
    (occupied / "existing_artifact.txt").write_text("pre-existing data")

    with pytest.raises(FileExistsError, match="Exclusive artifact directory required"):
        run_intent_correction_diagnostic(
            selected_cases=["final-case-03"],
            mode="mock",
            mock_gateway=mock_gateway,
            output_dir=occupied,
        )


def test_intent_correction_diagnostic_post_create_teardown(monkeypatch, tmp_path, mock_gateway):
    """Verifies isolated PostgreSQL schema is dropped even when error occurs after CREATE SCHEMA."""
    from apps.backend.platform.database import Database

    captured_schemas = []

    def failing_create_schema(self, *args, **kwargs):
        with self.engine.connect() as conn:
            curr_schema = conn.execute(text("SELECT current_schema()")).scalar()
            captured_schemas.append(curr_schema)
        raise RuntimeError("Simulated failure during Database.create_schema")

    monkeypatch.setattr(Database, "create_schema", failing_create_schema)

    out_dir = tmp_path / "diag_post_create_crash"
    target_schema = None
    try:
        with pytest.raises(RuntimeError, match="Simulated failure during Database.create_schema"):
            run_intent_correction_diagnostic(
                selected_cases=["final-case-03"],
                mode="mock",
                mock_gateway=mock_gateway,
                output_dir=out_dir,
            )

        assert len(captured_schemas) == 1
        target_schema = captured_schemas[0]

        # Verify target_schema was cleanly dropped by runner teardown
        owner_url, _ = resolve_database_url()
        owner = create_engine(owner_url)
        with owner.connect() as conn:
            schema_exists = conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": target_schema},
            ).scalar()
            assert schema_exists is None, f"Schema {target_schema} must be dropped after post-create failure!"
        owner.dispose()
    finally:
        # Prevent test schema leaks on assert failure
        if target_schema:
            try:
                owner_url, _ = resolve_database_url()
                owner = create_engine(owner_url)
                with owner.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{target_schema}" CASCADE'))
                owner.dispose()
            except Exception:
                pass


def test_intent_correction_diagnostic_teardown_error_recording(monkeypatch, tmp_path, mock_gateway):
    """When schema drop fails during cleanup, teardown failure is recorded and not claimed clean."""
    from sqlalchemy.engine import Connection

    real_execute = Connection.execute

    def mock_execute(self, statement, *args, **kwargs):
        stmt_str = str(statement)
        if "DROP SCHEMA" in stmt_str and "CASCADE" in stmt_str:
            raise RuntimeError("Simulated failure executing DROP SCHEMA CASCADE")
        return real_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", mock_execute)

    out_dir = tmp_path / "diag_teardown_error_run"
    created_schema = None
    try:
        res = run_intent_correction_diagnostic(
            selected_cases=["final-case-03"],
            mode="mock",
            mock_gateway=mock_gateway,
            output_dir=out_dir,
        )
        created_schema = res["created_schema"]

        summary = res["summary"]
        assert summary["teardown_success"] is False
        assert summary["teardown_error"] is not None
        assert "Simulated failure executing DROP SCHEMA CASCADE" in summary["teardown_error"]

        manifest = res["manifest"]
        assert manifest["teardown_success"] is False
        assert "Simulated failure executing DROP SCHEMA CASCADE" in manifest["teardown_error"]
    finally:
        # Clean up test schema
        monkeypatch.undo()
        if created_schema:
            try:
                owner_url, _ = resolve_database_url()
                owner = create_engine(owner_url)
                with owner.begin() as conn:
                    conn.execute(text(f'DROP SCHEMA IF EXISTS "{created_schema}" CASCADE'))
                owner.dispose()
            except Exception:
                pass


def test_intent_correction_diagnostic_no_correction_when_initial_draft_ready(tmp_path, mock_gateway, monkeypatch):
    """When initial suggestion is already draft_ready, no staff correction is executed."""
    # Offline loopback mock gateway test explicitly opts out of spaCy NER when en_core_web_sm is absent.
    monkeypatch.setenv("SUPPORTIQ_REQUIRE_PRIVACY_NER", "false")
    mock_gateway.set_initial_abstain_cases(set())

    out_dir = tmp_path / "diag_ready_run"
    res = run_intent_correction_diagnostic(
        selected_cases=["final-case-03"],
        mode="mock",
        mock_gateway=mock_gateway,
        output_dir=out_dir,
        poll_timeout=10.0,
        max_cases=12,
    )

    summary = res["summary"]
    assert summary["cases"] == 1
    assert summary["corrected"] == 0
    assert summary["assisted_drafts"] == 0
    assert summary["no_auto_send_all"] is True

    r = res["records"][0]
    assert r["initial"]["suggestion"]["draft_status"] == "draft_ready"
    assert r["correction_executed"] is False
    assert r["assisted"] is None
    assert r["override_audit"] == []


def test_main_cli_exits_non_zero_on_teardown_or_auto_send_failure(monkeypatch):
    """CLI exits with non-zero status code when teardown or no-auto-send invariant fails."""
    import sys

    # 1. Teardown failure -> exit code 1
    monkeypatch.setattr(
        "scripts.run_intent_correction_diagnostic.run_intent_correction_diagnostic",
        lambda **kwargs: {
            "output_dir": str(REPO_ROOT / "artifacts/evaluation/test"),
            "summary": {"teardown_success": False, "no_auto_send_all": True},
        },
    )
    monkeypatch.setattr(sys, "argv", ["run_intent_correction_diagnostic.py", "--mode", "mock"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1

    # 2. No-auto-send violation -> exit code 1
    monkeypatch.setattr(
        "scripts.run_intent_correction_diagnostic.run_intent_correction_diagnostic",
        lambda **kwargs: {
            "output_dir": str(REPO_ROOT / "artifacts/evaluation/test"),
            "summary": {"teardown_success": True, "no_auto_send_all": False},
        },
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1
