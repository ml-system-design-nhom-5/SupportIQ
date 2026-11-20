"""Unit & offline gate tests for Task C bounded Gemini 3.5 Flash-Lite acceptance runner."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI
import httpx
import pytest

from pipeline.evaluation import flash_lite_acceptance as fla
from pipeline.evaluation.live_provider_verification import (
    BudgetExhaustedBeforeNetworkError,
    BudgetGuardedTransport,
)
from scripts import run_flash_lite_acceptance as cli_runner


class _CountingInnerTransport(httpx.BaseTransport):
    def __init__(self) -> None:
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        return httpx.Response(200, json={"candidates": []}, request=request)


def test_shared_guard_enforces_24_cap_retries_zero_and_egress_before_network() -> None:
    default_guard = BudgetGuardedTransport(max_requests=fla.MAX_APPLICATION_LIVE_HTTP_REQUESTS)
    try:
        assert default_guard.max_requests == 24
        assert default_guard._retries_configured == 0
    finally:
        default_guard.close()

    inner = _CountingInnerTransport()
    guard = BudgetGuardedTransport(max_requests=24, inner=inner)
    adapter = fla._SharedGuardTransportAdapter(guard)
    client = httpx.Client(transport=adapter, trust_env=False, follow_redirects=False)
    try:
        gemini_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent"
        for idx in range(24):
            resp = client.post(gemini_url, json={"attempt": idx + 1})
            assert resp.status_code == 200
        assert inner.calls == 24
        assert guard.requests_attempted == 24
        assert guard.rejected_before_network_count == 0

        # 25th request must fail before hitting inner transport
        with pytest.raises(BudgetExhaustedBeforeNetworkError):
            client.post(gemini_url, json={"attempt": 25})
        assert inner.calls == 24
        assert guard.requests_attempted == 24
        assert guard.rejected_before_network_count == 1

        # Non-Gemini egress host must fail before network
        with pytest.raises(httpx.RequestError, match="Egress host is not allowed"):
            client.post("https://example.com/steal-key", json={})
        assert inner.calls == 24
    finally:
        adapter.close()
        client.close()
        guard.close()


def test_preflight_zero_live_calls_verifies_oof_and_model_without_secret_leak(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_secret = "AIzaSyFAKE-TASK-C-DO-NOT-LEAK-123456"
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"GEMINI_API_KEY={fake_secret}\nGEMINI_MODEL=gemini-3.5-flash-lite\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        fla,
        "_verify_pg_connectivity",
        lambda owner_url: {"connected": True, "server_version_prefix": "PostgreSQL 18.6 (mocked unit check)"},
    )
    monkeypatch.setattr(
        fla,
        "resolve_database_url",
        lambda _p: ("postgresql://postgres:synthetic@localhost:5432/supportiq", {}),
    )

    root_repo = fla.DEFAULT_ROOT_REPO
    if not (root_repo / "artifacts/models/trained/distilbert-supportiq/model.safetensors").exists():
        pytest.skip("Root trained serving model artifact not present in test environment")

    pre = fla.run_preflight(
        worktree_root=fla.REPO_ROOT,
        root_repo=root_repo,
        env_path=env_file,
        max_requests=24,
    )

    serialized = json.dumps(pre)
    assert fake_secret not in serialized
    assert pre["configured_provider"]["model"] == "gemini-3.5-flash-lite"
    assert pre["configured_provider"]["api_key_loaded_in_memory"] is True
    assert pre["configured_provider"]["api_key_persisted"] is False
    assert pre["budget_preflight"]["preflight_budget"] == "0/24"
    assert pre["budget_preflight"]["requests_attempted"] == 0
    assert pre["budget_preflight"]["transport_retries_configured"] == 0
    assert pre["serving_classifier"]["matches_pinned_expected_manifest"] is True

    oof = pre["oof_lineage_audit"]["distilbert_oof"]
    assert oof["total_rows"] == 37911
    assert oof["n_folds"] == 10
    assert oof["n_labels"] == 46
    assert oof["all_46_labels_present"] is True
    assert oof["meets_target_085"] is True
    assert oof["macro_f1_mean"] > 0.99

    srv = pre["oof_lineage_audit"]["serving_training_report_linkage"]
    assert srv["matches_oof_macro_f1_mean_within_1e12"] is True
    assert srv["matches_all_10_fold_metrics_within_1e12"] is True
    assert srv["train_sample_ids_sha256_match"] is True
    assert srv["train_sample_ids_exact_match_oof_sample_ids"] is True


def test_wrong_intent_separation_percentiles_and_strict_unknown_cost_accounting() -> None:
    app_records = [
        {
            "case_id": "final-case-01",
            "slice": "product_12_answerable",
            "terminal_status": "draft_ready",
            "correct_intent": True,
            "collection_success": True,
            "action_matches_expected": True,
            "authority_check_passed": True,
            "source_verification_passed": True,
            "customer_no_auto_send_observed": True,
            "submit_to_terminal_latency_ms": 1100.0,
            "is_success": True,
        },
        {
            "case_id": "final-case-02",
            "slice": "product_12_answerable",
            "terminal_status": "draft_ready",
            "correct_intent": False,  # wrong-intent draft must not count as correct-intent success
            "collection_success": True,
            "action_matches_expected": True,
            "authority_check_passed": True,
            "source_verification_passed": True,
            "customer_no_auto_send_observed": True,
            "submit_to_terminal_latency_ms": 1300.0,
            "is_success": False,
        },
        {
            "case_id": "final-case-03",
            "slice": "product_12_answerable",
            "terminal_status": "abstained",
            "correct_intent": False,
            "collection_success": True,
            "action_matches_expected": False,
            "authority_check_passed": True,
            "source_verification_passed": True,
            "customer_no_auto_send_observed": True,
            "submit_to_terminal_latency_ms": 100.0,
            "is_success": False,
        },
        {
            "case_id": "final-case-08",
            "slice": "product_12_answerable",
            "terminal_status": "llm_unavailable",
            "correct_intent": True,
            "collection_success": True,
            "action_matches_expected": False,
            "authority_check_passed": True,
            "source_verification_passed": True,
            "customer_no_auto_send_observed": True,
            "submit_to_terminal_latency_ms": 5020.0,
            "is_success": False,
        },
        {
            "case_id": "final-case-13",
            "slice": "sensitive_escalation",
            "terminal_status": "escalation_recommended",
            "correct_intent": True,
            "collection_success": True,
            "action_matches_expected": True,
            "authority_check_passed": True,
            "source_verification_passed": True,
            "customer_no_auto_send_observed": True,
            "submit_to_terminal_latency_ms": 95.0,
            "is_success": True,
        },
    ]
    app_metrics, fix_metrics = fla._summarize_phase1_metrics(app_records, [])
    assert app_metrics["answerable_correct_intent_count"] == 2
    assert app_metrics["answerable_automatic_raw_draft_ready_count"] == 2
    assert app_metrics["answerable_automatic_correct_intent_draft_ready_count"] == 1
    assert app_metrics["answerable_automatic_wrong_intent_draft_ready_count"] == 1
    assert app_metrics["answerable_automatic_wrong_intent_case_ids"] == ["final-case-02"]
    assert app_metrics["answerable_automatic_abstained_count"] == 1
    assert app_metrics["answerable_automatic_fallback_error_count"] == 1
    assert app_metrics["answerable_automatic_fallback_case_ids"] == ["final-case-08"]
    assert app_metrics["safety_unsafe_draft_count"] == 0
    assert app_metrics["error_rate_app_cases"] == 0.2
    assert fix_metrics["cases_submitted"] == 0

    pct = fla.compute_percentiles([100.0, 200.0, 300.0, 400.0, 5000.0])
    assert pct["p50_interpolated_ms"] == 300.0
    assert pct["p50_nearest_rank_ms"] == 300.0
    assert pct["p95_nearest_rank_ms"] == 5000.0
    assert pct["p95_interpolated_ms"] is not None

    tokens = fla.summarize_flash_lite_tokens_and_cost(
        [
            {"usage": {"promptTokenCount": 1000, "candidatesTokenCount": 200, "thoughtsTokenCount": 50, "totalTokenCount": 1250}},
            {"usage": {}},  # failed attempt omits usage
        ]
    )
    assert tokens["complete_cost_known"] is False
    assert tokens["invoice_verified"] is False
    assert tokens["complete_billed_cost_usd"] is None
    assert tokens["prompt_and_candidate_usage_present_all_attempts"] is False
    assert tokens["all_billable_token_fields_measured"] is False
    assert tokens["thought_tokens_measurement_status"] == "partial_measured"
    assert tokens["attempts_with_thought_tokens_omitted"] == 1
    assert tokens["observed_thought_tokens"] == 50
    assert tokens["attempts_missing_usage"] == 1
    assert "complete_tokens" not in tokens["cost_status"]
    # 1000 * 0.30/1M + (200 + 50) * 2.50/1M = 0.0003 + 0.000625 = 0.000925
    assert tokens["conditional_observed_list_price_usd"] == 0.000925

    omitted_thoughts = fla.summarize_flash_lite_tokens_and_cost(
        [
            {"usage": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120}}
            for _ in range(13)
        ]
    )
    assert omitted_thoughts["attempts_with_thought_tokens_field"] == 0
    assert omitted_thoughts["attempts_with_thought_tokens_omitted"] == 13
    assert omitted_thoughts["thought_tokens_measurement_status"] == "omitted_all_attempts"
    assert omitted_thoughts["observed_thought_tokens"] is None
    assert omitted_thoughts["all_billable_token_fields_measured"] is False
    assert omitted_thoughts["cost_status"] == "observed_candidate_only_thoughts_omitted_unknown_total"
    assert "complete_tokens" not in omitted_thoughts["cost_status"]
    assert omitted_thoughts["complete_cost_known"] is False
    assert omitted_thoughts["complete_billed_cost_usd"] is None


def test_postgres_schema_drop_failure_reporting_and_markdown() -> None:
    class _FailingConn:
        def execute(self, *args, **kwargs) -> None:
            raise RuntimeError("permission denied for schema accept_fl35_secret_user_pass=hunter2")

    class _FailingBegin:
        def __enter__(self):
            return _FailingConn()

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class _FailingEngine:
        def begin(self):
            return _FailingBegin()

    class _OkConn:
        def execute(self, *args, **kwargs) -> None:
            return None

    class _OkBegin:
        def __enter__(self):
            return _OkConn()

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    class _OkEngine:
        def begin(self):
            return _OkBegin()

    not_created = fla._drop_temporary_postgres_schema(_FailingEngine(), "accept_not_created", schema_created=False)
    assert not_created["postgres_schema_created"] is False
    assert not_created["postgres_schema_dropped_cleanly"] is None
    assert not_created["postgres_schema_drop_status"] == "not_created"

    failed = fla._drop_temporary_postgres_schema(_FailingEngine(), "accept_failed_drop", schema_created=True)
    assert failed["postgres_schema_created"] is True
    assert failed["postgres_schema_dropped_cleanly"] is False
    assert failed["postgres_schema_drop_status"] == "drop_failed"
    assert failed["postgres_schema_drop_error_category"] == "permission_denied"
    assert "hunter2" not in str(failed)

    succeeded = fla._drop_temporary_postgres_schema(_OkEngine(), "accept_ok_drop", schema_created=True)
    assert succeeded["postgres_schema_dropped_cleanly"] is True
    assert succeeded["postgres_schema_drop_status"] == "dropped_cleanly"
    assert succeeded["postgres_schema_drop_error_category"] is None

    p1_app, fix_m = fla._summarize_phase1_metrics([], [])
    base_report = {
        "run_id": "test-drop-fail",
        "generated_at": "2026-11-13T00:00:00Z",
        "git_commit": "abc1234",
        "isolated_runtime": {"configured_model": "gemini-3.5-flash-lite", **failed},
        "budget_accounting": {
            "authorized_max_http_requests": 24,
            "actual_http_requests_made": 0,
            "rejected_before_network_count": 0,
            "transport_retries_configured": 0,
            "budget_enforced_within_cap": True,
        },
        "phase1_primary_automatic_application": p1_app,
        "phase1_injected_component_boundaries": fix_m,
        "phase2_oracle_staff_override_diagnostic": {
            "cases_attempted": 0,
            "draft_ready_and_source_verified_count": 0,
            "fallback_or_failed_count": 0,
        },
        "phase3_long_timeout_component_diagnostic": {"executed": False, "note": "Not needed."},
        "combined_unique_answerable_correct_intent_drafts": {
            "automatic_only_count": 0,
            "automatic_plus_staff_override_count": 0,
            "case_ids": [],
        },
        "tokens_and_cost": fla.summarize_flash_lite_tokens_and_cost(
            [{"usage": {"promptTokenCount": 100, "candidatesTokenCount": 20, "totalTokenCount": 120}}]
        ),
        "oof_lineage_summary": {
            "distilbert_oof": {
                "oof_path": "artifacts/training/distilbert_cv/oof_predictions.csv",
                "total_rows": 37911,
                "n_folds": 10,
                "n_labels": 46,
                "macro_f1_mean": 0.995268,
                "macro_f1_std_ddof1": 0.001,
                "oof_macro_f1": 0.995,
            },
            "serving_training_report_linkage": {
                "matches_oof_macro_f1_mean_within_1e12": True,
                "matches_all_10_fold_metrics_within_1e12": True,
                "train_sample_ids_sha256_match": True,
            },
        },
    }
    md_failed = fla.render_flash_lite_markdown_report(base_report)
    assert "cleanup FAILED (error_category=permission_denied)" in md_failed
    assert "dropped cleanly" not in md_failed
    assert "unmeasured / omitted in all `1` attempts (not measured zero)" in md_failed

    base_report["isolated_runtime"] = {"configured_model": "gemini-3.5-flash-lite", **not_created}
    md_not_created = fla.render_flash_lite_markdown_report(base_report)
    assert "dropped cleanly" not in md_not_created
    assert "cleanup status=not_created" in md_not_created

    base_report["isolated_runtime"] = {"configured_model": "gemini-3.5-flash-lite", **succeeded}
    md_ok = fla.render_flash_lite_markdown_report(base_report)
    assert "(dropped cleanly; root ports `8080/8002` untouched)" in md_ok


def test_persist_run_outputs_hashes_markdown_and_refuses_secret_leak(tmp_path: Path) -> None:
    oof_stub = {
        "distilbert_oof": {
            "oof_path": "artifacts/training/distilbert_cv/oof_predictions.csv",
            "total_rows": 37911,
            "n_folds": 10,
            "n_labels": 46,
            "macro_f1_mean": 0.995268,
            "macro_f1_std_ddof1": 0.001,
            "oof_macro_f1": 0.995,
        },
        "serving_training_report_linkage": {
            "matches_oof_macro_f1_mean_within_1e12": True,
            "matches_all_10_fold_metrics_within_1e12": True,
            "train_sample_ids_sha256_match": True,
        },
    }
    p1_app, fix_m = fla._summarize_phase1_metrics([], [])
    report = {
        "run_id": "test-run-01",
        "generated_at": "2026-11-13T00:00:00Z",
        "git_commit": "abc1234",
        "isolated_runtime": {"configured_model": "gemini-3.5-flash-lite", "postgres_schema": "accept_test"},
        "budget_accounting": {
            "authorized_max_http_requests": 24,
            "actual_http_requests_made": 0,
            "rejected_before_network_count": 0,
            "transport_retries_configured": 0,
            "budget_enforced_within_cap": True,
        },
        "phase1_primary_automatic_application": p1_app,
        "phase1_injected_component_boundaries": fix_m,
        "phase2_oracle_staff_override_diagnostic": {
            "cases_attempted": 0,
            "draft_ready_and_source_verified_count": 0,
            "fallback_or_failed_count": 0,
        },
        "phase3_long_timeout_component_diagnostic": {"executed": False, "note": "Not needed."},
        "combined_unique_answerable_correct_intent_drafts": {
            "automatic_only_count": 0,
            "automatic_plus_staff_override_count": 0,
            "case_ids": [],
        },
        "tokens_and_cost": fla.summarize_flash_lite_tokens_and_cost([]),
        "oof_lineage_summary": oof_stub,
    }

    hashes = fla._persist_run_outputs(
        out_dir=tmp_path,
        report=report,
        phase1_app_records=[],
        phase1_fixture_records=[],
        phase2_override_records=[],
        secret_key="SUPER-SECRET-NEVER-LEAK",
    )
    assert "FLASH_LITE_ACCEPTANCE_REPORT.md" in hashes
    assert "flash_lite_acceptance_report.json" in hashes
    assert (tmp_path / "FLASH_LITE_ACCEPTANCE_REPORT.md").exists()

    report["leaked"] = "contains SUPER-SECRET-NEVER-LEAK inside"
    with pytest.raises(RuntimeError, match="secret API key detected"):
        fla._persist_run_outputs(
            out_dir=tmp_path,
            report=report,
            phase1_app_records=[],
            phase1_fixture_records=[],
            phase2_override_records=[],
            secret_key="SUPER-SECRET-NEVER-LEAK",
        )


def test_cli_refuses_max_requests_above_24() -> None:
    with pytest.raises(ValueError, match="must be between 0 and 24"):
        cli_runner.main(["--preflight-only", "--max-requests", "25"])


@pytest.mark.integration
def test_owned_isolated_ai_service_boots_and_restores_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import apps.ai_service.main as ai_main
    import apps.ml_inference.app as ml_app

    captured_env_during_boot: dict[str, str | None] = {}

    def _fake_create_app() -> FastAPI:
        captured_env_during_boot["GEMINI_MODEL"] = os.environ.get("GEMINI_MODEL")
        captured_env_during_boot["GEMINI_API_KEY"] = os.environ.get("GEMINI_API_KEY")
        captured_env_during_boot["SUPPORTIQ_ENABLE_LLM"] = os.environ.get("SUPPORTIQ_ENABLE_LLM")
        fake_app = FastAPI()

        @fake_app.get("/health/ready")
        def _ready() -> dict[str, object]:
            return {"status": "ready"}

        @fake_app.get("/v1/asset-versions")
        def _assets() -> dict[str, object]:
            return {"llm_model": captured_env_during_boot["GEMINI_MODEL"]}

        return fake_app

    monkeypatch.setattr(ai_main, "create_app", _fake_create_app)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    guard = BudgetGuardedTransport(max_requests=24, inner=_CountingInnerTransport())
    orig_model_dir = ml_app.MODEL_DIR
    orig_model_load = ml_app.ModelContainer.load
    try:
        with fla.owned_isolated_ai_service(
            api_key="FAKE-IN-MEM-KEY",
            model_name="gemini-3.5-flash-lite",
            model_dir=tmp_path,
            budget_guard=guard,
            startup_timeout_seconds=10.0,
        ) as gw:
            assert gw["health_ready"] == {"status": "ready"}
            assert gw["configured_model"] == "gemini-3.5-flash-lite"
            assert gw["asset_versions"] == {"llm_model": "gemini-3.5-flash-lite"}
            assert captured_env_during_boot["GEMINI_MODEL"] == "gemini-3.5-flash-lite"
            assert captured_env_during_boot["GEMINI_API_KEY"] == "FAKE-IN-MEM-KEY"
            # Secret must already be scrubbed from process environ while gateway serves requests
            assert os.environ.get("GEMINI_API_KEY") is None

        assert ml_app.MODEL_DIR == orig_model_dir
        assert ml_app.ModelContainer.load is orig_model_load
        assert os.environ.get("GEMINI_API_KEY") is None
        assert os.environ.get("GEMINI_MODEL") is None
    finally:
        guard.close()


def test_committed_flash_lite_acceptance_artifacts_integrity_and_budget() -> None:
    import hashlib

    eval_root = fla.REPO_ROOT / "artifacts" / "evaluation"
    run_dirs = [
        eval_root / "flash-lite-35-20261113-075914-153b01",
        eval_root / "flash-lite-35-20261113-080056-138721",
    ]
    cumulative_http = 0
    for rdir in run_dirs:
        assert rdir.exists(), f"Missing committed Flash-Lite artifact directory: {rdir}"
        hashes = json.loads((rdir / "report_hashes.json").read_text(encoding="utf-8"))
        for fname, expected_sha in hashes.items():
            fpath = rdir / fname
            assert fpath.exists(), f"Hashed file missing: {fpath}"
            actual_sha = hashlib.sha256(fpath.read_bytes()).hexdigest()
            assert actual_sha == expected_sha
            assert "AIza" not in fpath.read_text(encoding="utf-8")

        rep = json.loads((rdir / "flash_lite_acceptance_report.json").read_text(encoding="utf-8"))
        assert rep["budget_accounting"]["transport_retries_configured"] == 0
        assert rep["budget_accounting"]["budget_enforced_within_cap"] is True
        assert rep["phase1_primary_automatic_application"]["customer_no_auto_send_verified_all"] is True
        assert rep["phase1_primary_automatic_application"]["safety_unsafe_draft_count"] == 0
        assert rep["tokens_and_cost"]["complete_cost_known"] is False
        assert rep["tokens_and_cost"]["invoice_verified"] is False
        assert rep["tokens_and_cost"]["complete_billed_cost_usd"] is None
        cumulative_http += int(rep["budget_accounting"]["actual_http_requests_made"])

    assert cumulative_http == 18
    assert cumulative_http <= 24

    primary = json.loads((run_dirs[1] / "flash_lite_acceptance_report.json").read_text(encoding="utf-8"))
    assert primary["isolated_runtime"]["configured_model"] == "gemini-3.5-flash-lite"
    assert primary["isolated_runtime"]["root_ports_8080_8002_untouched"] is True
    assert primary["phase1_primary_automatic_application"]["cases_submitted"] == 20
    assert primary["phase1_primary_automatic_application"]["answerable_automatic_correct_intent_draft_ready_count"] == 4
    assert primary["phase1_primary_automatic_application"]["answerable_automatic_wrong_intent_draft_ready_count"] == 1
    assert primary["phase1_injected_component_boundaries"]["all_criteria_passed_count"] == 4
    assert primary["phase2_oracle_staff_override_diagnostic"]["cases_attempted"] == 8
    assert primary["phase2_oracle_staff_override_diagnostic"]["draft_ready_and_source_verified_count"] == 8
    assert primary["phase2_oracle_staff_override_diagnostic"]["no_auto_send_verified_all"] is True
    assert primary["combined_unique_answerable_correct_intent_drafts"]["automatic_plus_staff_override_count"] == 12


def test_committed_closure_gate_artifacts_hashes_and_reject_verdict() -> None:
    import hashlib

    gdir = fla.REPO_ROOT / "artifacts" / "evaluation" / "classifier_gate_task_a_closure_20261113"
    assert gdir.exists()
    hashes = json.loads((gdir / "report_hashes.json").read_text(encoding="utf-8"))
    for fname, expected_sha in hashes.items():
        fpath = gdir / fname
        assert fpath.exists()
        assert hashlib.sha256(fpath.read_bytes()).hexdigest() == expected_sha

    gate_rep = json.loads((gdir / "gate_report.json").read_text(encoding="utf-8"))
    supp = json.loads((gdir / "closure_supplement.json").read_text(encoding="utf-8"))
    assert gate_rep["gate_decision"] == "REJECT"
    assert gate_rep["failure_reasons"] == ["mandatory_escalation_unsafe_draft_leak"]
    assert gate_rep["candidate_calibrated_evaluation"]["ml_oos_80"]["false_draft_eligible_count"] == 0
    assert supp["independent_gate_decision"] == "REJECT"
    assert supp["rejector_runtime_parity"]["decision_mismatches"] == 0
