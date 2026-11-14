"""Task C bounded real-application acceptance & Gemini 3.5 Flash-Lite evidence runner.

Enforces:
- In-memory-only private API key loading (never printed, copied, or persisted to artifacts/git)
- Explicit owned runtime model selection: GEMINI_MODEL=gemini-3.5-flash-lite (no silent fallback)
- Global pre-network HTTP request cap (max 24 actual generation requests inclusive of all retries
  and optional separately labeled override / long-timeout diagnostics) via BudgetGuardedTransport
  with lower-layer transport retries=0 and pre-network refusal beyond 24
- Owned isolated FastAPI ai_service + isolated disposable PostgreSQL schema + synthetic seed accounts
  so root active services (ports 8080/8002) and user data remain untouched
- Offline verification of stored 10-fold OOF records and lineage (no retraining)
- Honest accounting: separates primary automatic application results, staff intent-override
  diagnostics, injected component boundaries, observed tokens vs unknown complete costs, and
  explicitly flags wrong-intent drafts vs correct-intent automatic drafts.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import socket
import threading
import time
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple
import uuid

from fastapi.testclient import TestClient
import httpx
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score
from sqlalchemy import create_engine, text
import uvicorn

from apps.backend.main import create_app as create_backend_app
from apps.backend.platform.config import Settings as BackendSettings
from apps.backend.platform.database import Database
from apps.backend.platform.models import Suggestion, Ticket
from apps.backend.seed import seed
from pipeline.evaluation.live_provider_verification import (
    ALLOWED_GEMINI_HOST,
    BudgetExhaustedBeforeNetworkError,
    BudgetGuardedTransport,
    load_private_provider_config,
    sanitize_text,
)
from pipeline.evaluation.ml_provenance_audit import (
    audit_baseline_oof,
    validate_oof_alignment,
)
from pipeline.preparation.utils import CORE_PRODUCT_INTENTS, STANDARD_INTENTS
from scripts.collect_final_acceptance_evidence import (
    AcceptanceEvidenceCollector,
    compute_bytes_sha256,
    compute_sha256,
    get_git_commit_hash,
    resolve_database_url,
)
from scripts.native_runtime import configure_runtime_environment

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT_REPO = Path(r"F:\Năm 3\SD\project\SupportIQ")
MAX_APPLICATION_LIVE_HTTP_REQUESTS = 24
FLASH_LITE_35_MODEL = "gemini-3.5-flash-lite"
FLASH_LITE_35_PRICING = {
    "provider": "google_ai_studio",
    "model": FLASH_LITE_35_MODEL,
    "tier": "standard_paid",
    "modality": "text",
    "input_cost_per_million": 0.30,
    "output_cost_per_million": 2.50,
    "output_includes_thinking": True,
    "source_url": "https://aistudio.google.com/docs/pricing",
    "verified_on": "2026-11-13",
    "note": (
        "Published standard paid-tier text token list rates for gemini-3.5-flash-lite "
        "(output rate includes thinking tokens); actual account billing tier/invoice is unverified."
    ),
}
VALID_APPLICATION_TERMINAL_STATES = {
    "draft_ready",
    "abstained",
    "escalation_recommended",
    "llm_unavailable",
    "unavailable",
}


def compute_percentiles(values_ms: List[float]) -> Dict[str, Optional[float]]:
    """Compute both standard linear-interpolated and nearest-rank percentiles without inventing missing samples."""
    clean = sorted(v for v in values_ms if v is not None and math.isfinite(v))
    if not clean:
        return {
            "count": 0,
            "p50_interpolated_ms": None,
            "p50_nearest_rank_ms": None,
            "p95_interpolated_ms": None,
            "p95_nearest_rank_ms": None,
            "max_ms": None,
        }
    n = len(clean)
    return {
        "count": n,
        "p50_interpolated_ms": round(float(np.percentile(clean, 50)), 4),
        "p50_nearest_rank_ms": round(float(clean[n // 2]), 4),
        "p95_interpolated_ms": round(float(np.percentile(clean, 95)), 4),
        "p95_nearest_rank_ms": round(float(clean[min(int(math.ceil(n * 0.95)) - 1, n - 1)]), 4),
        "max_ms": round(float(max(clean)), 4),
    }


def summarize_flash_lite_tokens_and_cost(
    attempts: List[Dict[str, Any]],
    *,
    configured_model: str = FLASH_LITE_35_MODEL,
) -> Dict[str, Any]:
    """Summarize observed Gemini 3.5 Flash-Lite tokens conservatively; never fabricate unknown billing totals."""
    observed_input = 0
    observed_output = 0
    observed_thoughts = 0
    observed_reported_total = 0
    missing_usage_attempts = 0
    attempts_with_thought_field = 0

    for att in attempts:
        usage = att.get("usage") or {}
        # Support both raw Gemini camelCase usageMetadata and Engine-mapped snake_case llm_usage
        p = usage.get("promptTokenCount") if "promptTokenCount" in usage else usage.get("input_tokens")
        c = usage.get("candidatesTokenCount") if "candidatesTokenCount" in usage else usage.get("output_tokens")
        t = usage.get("totalTokenCount") if "totalTokenCount" in usage else usage.get("total_tokens")
        th = usage.get("thoughtsTokenCount") if "thoughtsTokenCount" in usage else usage.get("thought_tokens")

        if type(p) is int and not isinstance(p, bool) and p >= 0:
            observed_input += p
        if type(c) is int and not isinstance(c, bool) and c >= 0:
            observed_output += c
        if type(th) is int and not isinstance(th, bool) and th >= 0:
            observed_thoughts += th
            attempts_with_thought_field += 1
        if type(t) is int and not isinstance(t, bool) and t >= 0:
            observed_reported_total += t

        if not (
            type(p) is int and not isinstance(p, bool)
            and type(c) is int and not isinstance(c, bool)
            and type(t) is int and not isinstance(t, bool)
        ):
            missing_usage_attempts += 1

    prompt_and_candidate_present_all = bool(attempts) and missing_usage_attempts == 0
    attempts_with_thought_omitted = max(0, len(attempts) - attempts_with_thought_field)
    all_billable_token_fields_measured = prompt_and_candidate_present_all and attempts_with_thought_omitted == 0
    if not attempts:
        thought_measurement_status = "no_attempts"
    elif attempts_with_thought_field == 0:
        thought_measurement_status = "omitted_all_attempts"
    elif attempts_with_thought_omitted > 0:
        thought_measurement_status = "partial_measured"
    else:
        thought_measurement_status = "all_attempts_measured"

    billable_output_observed = observed_output + observed_thoughts
    conditional_observed_usd = round(
        (observed_input / 1_000_000.0) * FLASH_LITE_35_PRICING["input_cost_per_million"]
        + (billable_output_observed / 1_000_000.0) * FLASH_LITE_35_PRICING["output_cost_per_million"],
        8,
    )
    if all_billable_token_fields_measured:
        cost_status = "observed_conditional_list_price_not_invoice"
        pricing_basis = "observed_prompt_candidate_and_measured_thoughts"
    elif prompt_and_candidate_present_all:
        cost_status = "observed_candidate_only_thoughts_omitted_unknown_total"
        pricing_basis = "observed_prompt_and_candidate_only_thoughts_omitted"
    else:
        cost_status = "incomplete_observed_usage_unknown_total"
        pricing_basis = "incomplete_observed_usage"

    return {
        "total_attempts_counted": len(attempts),
        "attempts_missing_usage": missing_usage_attempts,
        "attempts_with_thought_tokens_field": attempts_with_thought_field,
        "attempts_with_thought_tokens_omitted": attempts_with_thought_omitted,
        "thought_tokens_measurement_status": thought_measurement_status,
        "prompt_and_candidate_usage_present_all_attempts": prompt_and_candidate_present_all,
        "all_billable_token_fields_measured": all_billable_token_fields_measured,
        "observed_prompt_tokens": observed_input,
        "observed_candidate_tokens": observed_output,
        "observed_thought_tokens": observed_thoughts if attempts_with_thought_field > 0 else None,
        "observed_reported_total_tokens": observed_reported_total if prompt_and_candidate_present_all else None,
        "observed_partial_total_tokens": observed_reported_total,
        "complete_cost_known": False,
        "invoice_verified": False,
        "cost_status": cost_status,
        "conditional_observed_list_price_basis": pricing_basis,
        "conditional_observed_list_price_usd": conditional_observed_usd,
        "complete_billed_cost_usd": None,
        "list_price_reference_used": {**FLASH_LITE_35_PRICING, "configured_model": configured_model},
        "note": (
            "Conditional USD computed solely from observed tokens using published gemini-3.5-flash-lite list pricing "
            "($0.30/1M in, $2.50/1M out incl. thinking); omitted thoughtsTokenCount means unmeasured (not zero thinking), "
            "failed attempts may omit usageMetadata, complete billed cost is unknown, and actual account tier/invoice is unverified."
        ),
    }


def _categorize_cleanup_error(exc: Exception) -> str:
    """Map PostgreSQL schema cleanup exceptions to a bounded, credential-free category."""
    msg = f"{type(exc).__name__} {exc}".lower()
    if "permission" in msg or "insufficientprivilege" in msg:
        return "permission_denied"
    if "depend" in msg or "deadlock" in msg or "lock" in msg or "being accessed" in msg:
        return "active_dependency_or_lock"
    if "connection" in msg or "timeout" in msg or "operationalerror" in msg:
        return "connection_or_operational_error"
    if "programmingerror" in msg or "syntax" in msg:
        return "sql_programming_error"
    cls_slug = re.sub(r"[^a-z0-9_]+", "_", type(exc).__name__.lower()).strip("_")
    return f"db_{cls_slug or 'cleanup_error'}"


def _drop_temporary_postgres_schema(
    root_engine: Any,
    schema: str,
    *,
    schema_created: bool,
) -> Dict[str, Any]:
    """Drop an evaluation schema and return truthful observed cleanup status without leaking secrets."""
    if not schema_created:
        return {
            "postgres_schema": schema,
            "postgres_schema_created": False,
            "postgres_schema_dropped_cleanly": None,
            "postgres_schema_drop_status": "not_created",
            "postgres_schema_drop_error_category": None,
        }
    try:
        with root_engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    except Exception as exc:
        return {
            "postgres_schema": schema,
            "postgres_schema_created": True,
            "postgres_schema_dropped_cleanly": False,
            "postgres_schema_drop_status": "drop_failed",
            "postgres_schema_drop_error_category": _categorize_cleanup_error(exc),
        }
    return {
        "postgres_schema": schema,
        "postgres_schema_created": True,
        "postgres_schema_dropped_cleanly": True,
        "postgres_schema_drop_status": "dropped_cleanly",
        "postgres_schema_drop_error_category": None,
    }


def load_flash_lite_private_config(env_path: Path) -> Dict[str, Any]:
    """Load root .env GEMINI_API_KEY in memory only while explicitly selecting gemini-3.5-flash-lite."""
    cfg = load_private_provider_config(env_path)
    return {
        **cfg,
        "model": FLASH_LITE_35_MODEL,
        "env_gemini_model_value": cfg.get("model"),
        "env_file_exists": env_path.exists(),
        "env_path": str(env_path),
    }


def verify_stored_oof_lineage(
    worktree_root: Path = REPO_ROOT,
    root_repo: Path = DEFAULT_ROOT_REPO,
) -> Dict[str, Any]:
    """Inspect and cross-verify stored 10-fold OOF CSVs and serving model provenance without retraining."""
    baseline_audit = audit_baseline_oof(worktree_root, fail_closed=True)
    alignment_audit = validate_oof_alignment(worktree_root)

    dist_dir = worktree_root / "artifacts" / "training" / "distilbert_cv"
    oof_path = dist_dir / "oof_predictions.csv"
    fold_metrics_path = dist_dir / "fold_metrics.csv"
    if not oof_path.exists():
        raise FileNotFoundError(f"Stored DistilBERT OOF predictions missing: {oof_path}")
    if not fold_metrics_path.exists():
        raise FileNotFoundError(f"Stored DistilBERT fold_metrics.csv missing: {fold_metrics_path}")

    df_oof = pd.read_csv(oof_path)
    df_fold = pd.read_csv(fold_metrics_path)
    all_labels = sorted(STANDARD_INTENTS)
    actual_labels = sorted(df_oof["y_true"].unique().tolist())

    fold_rows: List[Dict[str, Any]] = []
    fold_f1s: List[float] = []
    max_fold_f1_delta = 0.0
    max_fold_acc_delta = 0.0
    for f in range(10):
        sub = df_oof[df_oof["fold"] == f]
        f1_val = float(f1_score(sub["y_true"], sub["y_pred"], labels=all_labels, average="macro", zero_division=0))
        acc_val = float(accuracy_score(sub["y_true"], sub["y_pred"]))
        fold_f1s.append(f1_val)
        csv_row = df_fold[df_fold["fold"] == f].iloc[0]
        max_fold_f1_delta = max(max_fold_f1_delta, abs(f1_val - float(csv_row["macro_f1"])))
        max_fold_acc_delta = max(max_fold_acc_delta, abs(acc_val - float(csv_row["accuracy"])))
        fold_rows.append(
            {
                "fold": f,
                "n_val_oof": int(len(sub)),
                "n_val_csv": int(csv_row["n_val"]),
                "macro_f1_recomputed": f1_val,
                "macro_f1_csv": float(csv_row["macro_f1"]),
                "accuracy_recomputed": acc_val,
                "accuracy_csv": float(csv_row["accuracy"]),
            }
        )

    macro_f1_mean = float(np.mean(fold_f1s))
    macro_f1_std_ddof0 = float(np.std(fold_f1s, ddof=0))
    macro_f1_std_ddof1 = float(np.std(fold_f1s, ddof=1))
    oof_macro_f1 = float(f1_score(df_oof["y_true"], df_oof["y_pred"], labels=all_labels, average="macro", zero_division=0))
    oof_accuracy = float(accuracy_score(df_oof["y_true"], df_oof["y_pred"]))

    from sklearn.metrics import classification_report
    rep = classification_report(df_oof["y_true"], df_oof["y_pred"], labels=all_labels, output_dict=True, zero_division=0)
    core_12_macro_f1 = float(np.mean([rep[lbl]["f1-score"] for lbl in sorted(CORE_PRODUCT_INTENTS)]))

    serving_dir = root_repo / "artifacts" / "models" / "trained" / "distilbert-supportiq"
    training_report_path = serving_dir / "training_report.json"
    sample_ids_path = serving_dir / "train_sample_ids.json"

    serving_linkage: Dict[str, Any] = {
        "serving_dir": str(serving_dir),
        "training_report_exists": training_report_path.exists(),
        "train_sample_ids_exists": sample_ids_path.exists(),
    }
    if training_report_path.exists():
        tr = json.loads(training_report_path.read_text(encoding="utf-8"))
        tr_folds = tr.get("fold_metrics", [])
        tr_mean = tr.get("cv_macro_f1_mean")
        fold_report_match = len(tr_folds) == 10 and all(
            abs(float(tr_folds[i]["macro_f1"]) - fold_rows[i]["macro_f1_recomputed"]) < 1e-12
            and abs(float(tr_folds[i]["accuracy"]) - fold_rows[i]["accuracy_recomputed"]) < 1e-12
            and int(tr_folds[i]["n_val"]) == fold_rows[i]["n_val_oof"]
            for i in range(10)
        )
        serving_linkage.update(
            {
                "training_report_created_at": tr.get("created_at"),
                "training_report_cv_protocol": tr.get("cv_protocol"),
                "training_report_cv_n_folds": tr.get("cv_n_folds"),
                "training_report_train_samples": tr.get("train_samples"),
                "training_report_cv_macro_f1_mean": tr_mean,
                "training_report_cv_macro_f1_std_ddof1": tr.get("cv_macro_f1_std"),
                "matches_oof_macro_f1_mean_within_1e12": (
                    tr_mean is not None and abs(float(tr_mean) - macro_f1_mean) < 1e-12
                ),
                "matches_all_10_fold_metrics_within_1e12": fold_report_match,
                "training_report_git_commit_recorded": bool(tr.get("git_commit")),
            }
        )
        mem = tr.get("membership_evidence") or {}
        if sample_ids_path.exists():
            actual_ids_sha = compute_sha256(sample_ids_path).upper()
            expected_ids_sha = str(mem.get("sha256", "")).upper()
            ids_data = json.loads(sample_ids_path.read_text(encoding="utf-8"))
            if isinstance(ids_data, list):
                id_list = ids_data
            elif isinstance(ids_data, dict):
                id_list = ids_data.get("train_sample_ids") or ids_data.get("sample_ids") or ids_data.get("ids") or []
            else:
                id_list = []
            serving_linkage.update(
                {
                    "train_sample_ids_sha256_actual": actual_ids_sha,
                    "train_sample_ids_sha256_expected": expected_ids_sha,
                    "train_sample_ids_sha256_match": (actual_ids_sha == expected_ids_sha),
                    "train_sample_ids_count": len(id_list),
                    "train_sample_ids_exact_match_oof_sample_ids": (
                        set(map(str, id_list)) == set(df_oof["sample_id"].astype(str))
                    ),
                }
            )

    missing_lineage_items = []
    if not (dist_dir / "manifest.json").exists():
        missing_lineage_items.append(
            "artifacts/training/distilbert_cv/manifest.json hashing oof_predictions.csv/fold_metrics.csv is absent"
        )
    if not serving_linkage.get("training_report_git_commit_recorded"):
        missing_lineage_items.append(
            "serving distilbert-supportiq/training_report.json does not record a git_commit hash"
        )
    missing_lineage_items.append(
        "individual 10-fold DistilBERT fold model weight checkpoints are not stored in the repository (only final refitted serving distilbert-supportiq weights + train_sample_ids + 37,911 OOF CSVs)"
    )

    return {
        "evidence_kind": "cached_recomputed_with_serving_report_cross_check",
        "new_training_executed": False,
        "records_present_and_verified": True,
        "baseline_audit": {
            "manifest_path": baseline_audit["manifest_path"],
            "oof_path": baseline_audit["oof_path"],
            "manifest_hash_match": baseline_audit["manifest_hash_match"],
            "n_folds": baseline_audit["n_folds"],
            "n_labels": baseline_audit["n_labels"],
            "candidates": baseline_audit["candidates"],
        },
        "distilbert_oof": {
            "oof_path": str(oof_path.relative_to(worktree_root)),
            "fold_metrics_path": str(fold_metrics_path.relative_to(worktree_root)),
            "oof_sha256": compute_sha256(oof_path),
            "fold_metrics_sha256": compute_sha256(fold_metrics_path),
            "total_rows": int(len(df_oof)),
            "unique_sample_ids": int(df_oof["sample_id"].nunique()),
            "n_folds": int(df_oof["fold"].nunique()),
            "n_labels": len(actual_labels),
            "all_46_labels_present": set(actual_labels) == set(STANDARD_INTENTS),
            "macro_f1_mean": macro_f1_mean,
            "macro_f1_std_ddof0": macro_f1_std_ddof0,
            "macro_f1_std_ddof1": macro_f1_std_ddof1,
            "oof_macro_f1": oof_macro_f1,
            "oof_accuracy": oof_accuracy,
            "core_12_intents_macro_f1": core_12_macro_f1,
            "meets_target_085": bool(macro_f1_mean >= 0.85),
            "max_fold_f1_delta_vs_fold_metrics_csv": max_fold_f1_delta,
            "max_fold_acc_delta_vs_fold_metrics_csv": max_fold_acc_delta,
            "alignment_with_baseline_oof": alignment_audit,
        },
        "serving_training_report_linkage": serving_linkage,
        "missing_lineage_gaps": missing_lineage_items,
    }


class _SharedGuardTransportAdapter(httpx.BaseTransport):
    """Delegating transport used inside owned isolated ai_service lifespan so shared guard state persists."""

    def __init__(self, guard: BudgetGuardedTransport) -> None:
        self._guard = guard

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._guard.handle_request(request)

    def close(self) -> None:
        # Shared guard lifecycle is managed explicitly by OwnedIsolatedAiGateway / runner
        return None


def _pick_free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


@contextmanager
def owned_isolated_ai_service(
    *,
    api_key: str,
    model_name: str,
    model_dir: Path,
    budget_guard: BudgetGuardedTransport,
    host: str = "127.0.0.1",
    startup_timeout_seconds: float = 45.0,
) -> Iterator[Dict[str, Any]]:
    """Launch an owned isolated apps.ai_service FastAPI instance over loopback HTTP.

    Does NOT edit production files and restores patched module attributes and environment vars cleanly on exit.
    Does NOT touch root services on ports 8080/8002.
    """
    import apps.ai_service.main as ai_main
    import apps.ml_inference.app as ml_app

    orig_model_dir = ml_app.MODEL_DIR
    orig_model_load = ml_app.ModelContainer.load
    orig_transport_cls = ai_main.AllowListedTransport
    orig_env = {
        k: os.environ.get(k)
        for k in ("GEMINI_API_KEY", "GEMINI_MODEL", "SUPPORTIQ_ENABLE_LLM")
    }

    port = _pick_free_local_port()
    base_url = f"http://{host}:{port}"
    target_model_dir = Path(model_dir)

    os.environ["GEMINI_API_KEY"] = api_key
    os.environ["GEMINI_MODEL"] = model_name
    os.environ["SUPPORTIQ_ENABLE_LLM"] = "true"
    ml_app.MODEL_DIR = target_model_dir

    def _isolated_model_load(
        self_container: Any,
        load_dir: Optional[Path] = None,
        calibration_manifest_path: Optional[Path] = None,
    ) -> Any:
        # ModelContainer.load binds default arg MODEL_DIR at import time, so pass target_model_dir explicitly.
        resolved_dir = target_model_dir if (load_dir is None or load_dir == orig_model_dir) else load_dir
        return orig_model_load(self_container, model_dir=resolved_dir, calibration_manifest_path=calibration_manifest_path)

    ml_app.ModelContainer.load = _isolated_model_load  # type: ignore[method-assign]
    ai_main.AllowListedTransport = lambda: _SharedGuardTransportAdapter(budget_guard)  # type: ignore[assignment]

    try:
        app = ai_main.create_app()
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True, name=f"owned-ai-gateway-{port}")
        thread.start()

        deadline = time.monotonic() + startup_timeout_seconds
        ready_payload: Optional[Dict[str, Any]] = None
        assets_payload: Optional[Dict[str, Any]] = None
        last_err: Optional[str] = None
        with httpx.Client(timeout=2.0, trust_env=False) as probe:
            while time.monotonic() < deadline:
                if not thread.is_alive():
                    raise RuntimeError(f"Owned isolated AI gateway thread exited prematurely ({last_err})")
                try:
                    r = probe.get(f"{base_url}/health/ready")
                    if r.status_code == 200:
                        ready_payload = r.json()
                        v = probe.get(f"{base_url}/v1/asset-versions")
                        if v.status_code == 200:
                            assets_payload = v.json()
                        break
                    last_err = f"HTTP {r.status_code}"
                except Exception as exc:
                    last_err = type(exc).__name__
                time.sleep(0.15)
        if not ready_payload:
            server.should_exit = True
            thread.join(timeout=5.0)
            raise RuntimeError(f"Owned isolated AI gateway failed readiness check within {startup_timeout_seconds}s: {last_err}")

        # Scrub process env once AiSettings & lifespan captured the in-memory client credentials
        for k, prev in orig_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev

        try:
            yield {
                "base_url": base_url,
                "port": port,
                "health_ready": ready_payload,
                "asset_versions": assets_payload or {},
                "configured_model": model_name,
            }
        finally:
            server.should_exit = True
            thread.join(timeout=10.0)
    finally:
        ml_app.MODEL_DIR = orig_model_dir
        ml_app.ModelContainer.load = orig_model_load  # type: ignore[method-assign]
        ai_main.AllowListedTransport = orig_transport_cls
        for k, prev in orig_env.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def verify_serving_model_directory(model_dir: Path) -> Dict[str, Any]:
    """Verify serving DistilBERT model artifact SHA-256 digests without loading GPU or touching live endpoints."""
    from apps.ml_inference.app import EXPECTED_MANIFEST

    model_file = model_dir / "model.safetensors"
    tok_file = model_dir / "tokenizer.json"
    cfg_file = model_dir / "config.json"
    if not (model_file.exists() and tok_file.exists() and cfg_file.exists()):
        raise FileNotFoundError(f"Serving DistilBERT model files missing under {model_dir}")
    w_sha = compute_sha256(model_file).lower()
    t_sha = compute_sha256(tok_file).lower()
    c_sha = compute_sha256(cfg_file).lower()
    matches_expected = (
        w_sha == EXPECTED_MANIFEST["weights_sha256"].lower()
        and t_sha == EXPECTED_MANIFEST["tokenizer_sha256"].lower()
    )
    return {
        "model_dir": str(model_dir),
        "model_version": EXPECTED_MANIFEST["model_version"],
        "weights_sha256": w_sha,
        "tokenizer_sha256": t_sha,
        "config_sha256": c_sha,
        "matches_pinned_expected_manifest": matches_expected,
    }


def _verify_pg_connectivity(owner_url: str) -> Dict[str, Any]:
    eng = create_engine(owner_url, hide_parameters=True)
    try:
        with eng.connect() as conn:
            ver = str(conn.execute(text("SELECT version()")).scalar() or "")
        return {"connected": True, "server_version_prefix": ver[:60]}
    finally:
        eng.dispose()


def _inspect_case_citations(
    raw_citations: List[Dict[str, Any]],
    raw_analysis_docs: List[Dict[str, Any]],
    executed_order_context: Dict[str, Any],
    helper_collector: AcceptanceEvidenceCollector,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    snapshots: Dict[str, Any] = {}
    parsed_citations: List[Dict[str, Any]] = []

    for cit in raw_citations:
        src_type = cit.get("source_type")
        if src_type in ("order_context", "order"):
            f_name = cit.get("field")
            f_val = cit.get("value")
            field_present = executed_order_context is not None and f_name in executed_order_context
            val_matches = field_present and (executed_order_context[f_name] == f_val)
            v_ok = bool(field_present and val_matches)
            parsed_citations.append(
                {
                    "source_type": "order_context",
                    "field": f_name,
                    "value": f_val,
                    "field_present_in_executed_context": field_present,
                    "value_matches_executed_context": val_matches,
                    "is_verified": v_ok,
                }
            )
        else:
            d_id = cit.get("doc_id") or cit.get("document_id")
            d_ver = cit.get("version")
            ret_hash = cit.get("content_hash")
            snap = (
                helper_collector._build_source_snapshot(
                    doc_id=d_id,
                    version=d_ver,
                    returned_content_hash=ret_hash,
                    is_injected=False,
                )
                if d_id
                else None
            )
            if snap:
                snapshots[f"{d_id}:{d_ver or snap['version']}"] = snap
            parsed_citations.append(
                {
                    "source_type": "document",
                    "document_id": d_id,
                    "version": d_ver,
                    "content_hash": ret_hash,
                    "is_verified": snap["is_verified"] if snap else False,
                    "verification_error": snap["verification_error"] if snap else "SNAPSHOT_CREATION_FAILED",
                }
            )

    for doc_ret in raw_analysis_docs:
        d_id = doc_ret.get("document_id") or doc_ret.get("doc_id")
        d_ver = doc_ret.get("version")
        ret_hash = doc_ret.get("content_hash")
        if d_id and f"{d_id}:{d_ver}" not in snapshots:
            snap = helper_collector._build_source_snapshot(
                doc_id=d_id,
                version=d_ver,
                returned_content_hash=ret_hash,
                is_injected=False,
            )
            snapshots[f"{d_id}:{d_ver or snap['version']}"] = snap

    return parsed_citations, snapshots


def _poll_ticket_suggestion(
    staff: TestClient,
    ticket_id: str,
    *,
    poll_timeout_seconds: float,
    expected_suggestion_id: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    deadline = time.monotonic() + poll_timeout_seconds
    suggestion_data: Dict[str, Any] = {}
    while time.monotonic() < deadline:
        resp = staff.get(f"/v1/console/tickets/{ticket_id}")
        if resp.status_code == 200:
            suggestion_data = resp.json().get("suggestion", {}) or {}
            sid_ok = expected_suggestion_id is None or suggestion_data.get("suggestion_id") == expected_suggestion_id
            a_stat = suggestion_data.get("analysis_status", "pending")
            d_stat = suggestion_data.get("draft_status", "pending")
            if sid_ok and a_stat != "pending" and d_stat != "pending":
                return True, suggestion_data
        time.sleep(0.05)
    return False, suggestion_data


def _observe_customer_ticket(customer: TestClient, ticket_id: str) -> Dict[str, Any]:
    cust_resp = customer.get(f"/v1/shop/tickets/{ticket_id}")
    out = {
        "customer_http_status": cust_resp.status_code,
        "customer_json_valid": False,
        "customer_reply_is_none": False,
        "customer_no_auto_send_observed": False,
        "observation_error": None,
    }
    if cust_resp.status_code != 200:
        out["observation_error"] = f"CUSTOMER_HTTP_{cust_resp.status_code}"
        return out
    data = cust_resp.json()
    if not isinstance(data, dict) or data.get("ticket_id") != ticket_id or "reply" not in data:
        out["observation_error"] = "MISSING_REPLY_FIELD_OR_TICKET_ID_MISMATCH"
        return out
    reply_none = data.get("reply") is None
    status_recv = data.get("customer_status") == "received"
    out["customer_json_valid"] = True
    out["customer_reply_is_none"] = reply_none
    out["customer_no_auto_send_observed"] = bool(reply_none and status_recv)
    return out


def _build_record_from_suggestion(
    *,
    phase: str,
    case: Dict[str, Any],
    ticket_id: str,
    wall_latency_ms: float,
    reached_terminal: bool,
    suggestion_data: Dict[str, Any],
    cust_obs: Dict[str, Any],
    executed_order_context: Dict[str, Any],
    executed_as_of: Optional[str],
    helper_collector: AcceptanceEvidenceCollector,
    secret_key: str,
) -> Dict[str, Any]:
    raw_analysis = suggestion_data.get("analysis") or {}
    raw_routing = raw_analysis.get("routing") or {}
    raw_intent = raw_analysis.get("intent") or {}
    versions = suggestion_data.get("versions") or raw_analysis.get("versions") or {}
    step_latencies = suggestion_data.get("step_latency_ms") or {}
    usage_meta = suggestion_data.get("llm_usage") or {}
    llm_meta = suggestion_data.get("llm_metadata") or {}
    draft_payload = suggestion_data.get("draft") or {}
    full_draft_text = sanitize_text(draft_payload.get("text"), secret_key) if draft_payload.get("text") else None
    raw_citations = draft_payload.get("citations") or []

    parsed_citations, snapshots = _inspect_case_citations(
        raw_citations,
        raw_analysis.get("documents") or [],
        executed_order_context,
        helper_collector,
    )

    terminal_status = suggestion_data.get("draft_status", "timeout") if reached_terminal else "timeout"
    predicted_label = raw_intent.get("label")
    correct_intent = bool(predicted_label == case.get("intent"))
    actual_reasons = sorted(
        set(raw_routing.get("reason_codes") or []) | set(suggestion_data.get("reason_codes") or [])
    )
    expected_reasons = case.get("expected_reasons") or []
    reasons_match = all(r in actual_reasons for r in expected_reasons) if expected_reasons else True

    exp_action = case.get("expected_action")
    if exp_action == "draft":
        action_matches = terminal_status == "draft_ready"
    elif exp_action == "escalate":
        action_matches = terminal_status == "escalation_recommended"
    elif exp_action == "abstain":
        action_matches = terminal_status == "abstained"
    else:
        action_matches = False

    if case.get("slice") == "sensitive_escalation" or "requires_authority" in expected_reasons:
        authority_ok = "requires_authority" in actual_reasons
    else:
        authority_ok = True

    all_cits_ok = all(c.get("is_verified", False) for c in parsed_citations) if parsed_citations else True
    all_snaps_ok = all(s.get("is_verified", False) for s in snapshots.values()) if snapshots else True
    if exp_action == "draft":
        has_expected_docs = all(
            any((s.get("doc_id") == doc.split(":")[0] or s.get("document_id") == doc.split(":")[0]) for s in snapshots.values())
            for doc in (case.get("expected_docs") or [])
        )
        source_ok = bool(snapshots) and all_snaps_ok and all_cits_ok and has_expected_docs
    else:
        source_ok = all_snaps_ok and all_cits_ok

    collection_success = (
        reached_terminal
        and cust_obs["customer_json_valid"]
        and cust_obs["customer_no_auto_send_observed"]
        and math.isfinite(wall_latency_ms)
        and wall_latency_ms > 0
        and terminal_status in VALID_APPLICATION_TERMINAL_STATES
    )
    # Primary acceptance requires collection_success, expected action, reasons, authority, verified sources,
    # AND for answerable product cases in automatic mode, correct predicted intent + actual draft_ready
    all_criteria_passed = bool(
        collection_success
        and action_matches
        and reasons_match
        and authority_ok
        and source_ok
        and (correct_intent if exp_action == "draft" else True)
    )

    attempts = list(llm_meta.get("attempts") or [])
    return {
        "phase": phase,
        "case_id": case["id"],
        "slice": case["slice"],
        "category": case.get("category"),
        "fixture_boundary": case["fixture_boundary"],
        "component_evidence": "application_postgresql_gateway",
        "query": case["query"],
        "expected_intent": case["intent"],
        "expected_action": exp_action,
        "expected_docs": case.get("expected_docs", []),
        "expected_reasons": expected_reasons,
        "order_id": case.get("order_id"),
        "actual_executed_order_context": executed_order_context,
        "actual_executed_as_of": executed_as_of,
        "ticket_id": ticket_id,
        "suggestion_id": suggestion_data.get("suggestion_id"),
        "intent_source": raw_intent.get("source"),
        "predicted_intent": predicted_label,
        "intent_confidence": raw_intent.get("probability"),
        "intent_score_kind": raw_intent.get("score_kind"),
        "correct_intent": correct_intent,
        "submit_to_terminal_latency_ms": round(float(wall_latency_ms), 2),
        "terminal_status": terminal_status,
        "analysis_status": suggestion_data.get("analysis_status", "unknown"),
        "draft_status": suggestion_data.get("draft_status", "unknown"),
        "failure_code": suggestion_data.get("failure_code"),
        "reason_codes": actual_reasons,
        "customer_no_auto_send_observed": cust_obs["customer_no_auto_send_observed"],
        "customer_reply_is_none": cust_obs["customer_reply_is_none"],
        "customer_http_status": cust_obs["customer_http_status"],
        "response_versions": versions,
        "llm_metadata": llm_meta,
        "reported_llm_model": llm_meta.get("model"),
        "reported_llm_model_version": llm_meta.get("model_version"),
        "usage_metadata": usage_meta,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "step_latencies_ms": step_latencies,
        "full_draft_text": full_draft_text,
        "citations": parsed_citations,
        "source_snapshots": snapshots,
        "staff_note": sanitize_text(suggestion_data.get("staff_note"), secret_key) if suggestion_data.get("staff_note") else None,
        "raw_model_routing": {
            "intent": raw_intent,
            "routing": raw_routing,
            "alternatives": raw_analysis.get("alternatives", []),
            "warnings": raw_analysis.get("warnings", []),
        },
        "collection_success": collection_success,
        "action_matches_expected": action_matches,
        "reasons_match_expected": reasons_match,
        "authority_check_passed": authority_ok,
        "source_verification_passed": source_ok,
        "is_success": all_criteria_passed,
    }


def _evaluate_injected_fixture_case(
    case: Dict[str, Any],
    helper_collector: AcceptanceEvidenceCollector,
) -> Dict[str, Any]:
    t0 = time.perf_counter()
    retrieved = helper_collector._run_injected_fixture_retrieval(case)
    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    retriever_status = retrieved.get("status", "unknown")
    retriever_healthy = retriever_status in ("success", "no_match", "empty_kb") and retriever_status != "encoder_unavailable"
    evidence = retrieved.get("evidence", [])
    has_conflict = bool(retrieved.get("has_conflict", False))

    component_reasons: List[str] = []
    expiry_ok = False
    conflict_ok = False
    if case["slice"] == "expired_injected_boundary":
        target_doc_id = "POL-INJ-EXP-01" if case["id"] == "final-case-21" else "POL-INJ-EXP-02"
        doc_meta = next((d for d in helper_collector.injected_docs_raw if (d.get("doc_id") or d.get("document_id")) == target_doc_id), {})
        expiry_ok = retriever_healthy and len(evidence) == 0 and (doc_meta.get("valid_to", "") < case.get("as_of", ""))
        if expiry_ok:
            component_reasons = ["only_expired_documents", "no_valid_document"]
    elif case["slice"] == "conflict_injected_boundary":
        conflict_ok = retriever_healthy and has_conflict and len(evidence) >= 2
        if conflict_ok:
            component_reasons = ["conflicting_sources"]

    snapshots = {}
    for doc in helper_collector.injected_docs_raw:
        d_id = doc.get("doc_id") or doc.get("document_id")
        if d_id and d_id in case.get("notes", ""):
            snap = helper_collector._build_source_snapshot(
                doc_id=d_id,
                version=doc.get("version", "1.0"),
                returned_content_hash=doc.get("content_hash"),
                is_injected=True,
            )
            snapshots[f"{d_id}:{snap['version']}"] = snap

    all_snaps_ok = bool(snapshots) and all(s.get("is_verified", False) for s in snapshots.values())
    reasons_match = all(r in component_reasons for r in (case.get("expected_reasons") or []))
    collection_success = retriever_healthy and math.isfinite(latency_ms) and latency_ms > 0
    passed = bool(
        collection_success
        and all_snaps_ok
        and reasons_match
        and (expiry_ok if case["slice"] == "expired_injected_boundary" else conflict_ok)
    )
    return {
        "phase": "component_injected_boundary",
        "case_id": case["id"],
        "slice": case["slice"],
        "category": case.get("category"),
        "fixture_boundary": case["fixture_boundary"],
        "component_evidence": "retrieval_adapter_injected_fixture_execution",
        "query": case["query"],
        "expected_intent": case["intent"],
        "expected_action": "abstain",
        "expected_reasons": case.get("expected_reasons", []),
        "submit_to_terminal_latency_ms": latency_ms,
        "terminal_status": f"component_retriever_{retriever_status}",
        "customer_no_auto_send_observed": None,
        "customer_reply_is_none": None,
        "customer_http_status": None,
        "reason_codes": component_reasons,
        "source_snapshots": snapshots,
        "encoder_provenance": getattr(helper_collector, "encoder_provenance", "unknown"),
        "collection_success": collection_success,
        "action_matches_expected": None,
        "reasons_match_expected": reasons_match,
        "authority_check_passed": None,
        "source_verification_passed": all_snaps_ok,
        "is_success": passed,
    }


def run_preflight(
    *,
    worktree_root: Path = REPO_ROOT,
    root_repo: Path = DEFAULT_ROOT_REPO,
    env_path: Optional[Path] = None,
    max_requests: int = MAX_APPLICATION_LIVE_HTTP_REQUESTS,
) -> Dict[str, Any]:
    """Run zero-network preflight verifying private config, OOF lineage, serving model, suite hashes, and DB."""
    configure_runtime_environment()
    resolved_env = env_path or (root_repo / ".env")
    cfg = load_flash_lite_private_config(resolved_env)
    model_dir = root_repo / "artifacts" / "models" / "trained" / "distilbert-supportiq"
    serving_info = verify_serving_model_directory(model_dir)
    helper_collector = AcceptanceEvidenceCollector(
        mode="live",
        suite_path=worktree_root / "data/benchmarks/final_acceptance/cases.jsonl",
        manifest_path=worktree_root / "data/benchmarks/final_acceptance/suite_manifest.json",
        fixtures_path=worktree_root / "data/benchmarks/final_acceptance/injected_robustness_fixtures.json",
        paired_tasks_path=worktree_root / "data/benchmarks/final_acceptance/paired_agent_tasks.json",
        active_kb_path=worktree_root / "data/knowledge/approved_kb.v2.json",
        release_path=worktree_root / "apps/ai_service/kb-release.json",
        mock_orders_path=worktree_root / "data/knowledge/mock_orders.json",
    )
    oof_lineage = verify_stored_oof_lineage(worktree_root=worktree_root, root_repo=root_repo)
    owner_url, _ = resolve_database_url(str(root_repo / ".local" / "application.json"))
    pg_check = _verify_pg_connectivity(owner_url)
    guard = BudgetGuardedTransport(max_requests=max_requests)
    try:
        preflight_budget_state = {
            "preflight_budget": f"{guard.requests_attempted}/{guard.max_requests}",
            "authorized_max_http_requests": guard.max_requests,
            "requests_attempted": guard.requests_attempted,
            "rejected_before_network_count": guard.rejected_before_network_count,
            "transport_retries_configured": guard._retries_configured,
        }
    finally:
        guard.close()

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit_hash(),
        "mode": "preflight_zero_live_calls",
        "configured_provider": {
            "provider": "google_ai_studio",
            "model": cfg["model"],
            "env_model_value": cfg.get("env_gemini_model_value"),
            "env_file_exists": cfg["env_file_exists"],
            "api_key_loaded_in_memory": bool(cfg.get("api_key")),
            "api_key_persisted": False,
        },
        "serving_classifier": serving_info,
        "suite_and_kb_provenance": {
            "total_frozen_cases": len(helper_collector.cases),
            "manifest_cases_sha256": helper_collector.manifest_cases_sha256,
            "matched_kb_provenance": helper_collector.matched_kb_provenance,
            "matched_line_ending": helper_collector.matched_line_ending,
        },
        "postgres_isolated_connectivity": pg_check,
        "budget_preflight": preflight_budget_state,
        "oof_lineage_audit": oof_lineage,
    }


def _summarize_phase1_metrics(
    app_records: List[Dict[str, Any]],
    fixture_records: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    answerable = [r for r in app_records if r["slice"] == "product_12_answerable"]
    safety = [r for r in app_records if r["slice"] != "product_12_answerable"]

    auto_raw_drafts = [r for r in answerable if r["terminal_status"] == "draft_ready"]
    auto_correct_drafts = [r for r in auto_raw_drafts if r["correct_intent"]]
    auto_wrong_drafts = [r for r in auto_raw_drafts if not r["correct_intent"]]
    auto_abstained = [r for r in answerable if r["terminal_status"] == "abstained"]
    auto_fallback_errors = [r for r in answerable if r["terminal_status"] in ("llm_unavailable", "unavailable", "timeout")]

    safety_unsafe_drafts = [r for r in safety if r["terminal_status"] == "draft_ready"]
    app_latencies = [float(r["submit_to_terminal_latency_ms"]) for r in app_records if r.get("submit_to_terminal_latency_ms") is not None]
    ans_latencies = [float(r["submit_to_terminal_latency_ms"]) for r in answerable if r.get("submit_to_terminal_latency_ms") is not None]
    fix_latencies = [float(r["submit_to_terminal_latency_ms"]) for r in fixture_records if r.get("submit_to_terminal_latency_ms") is not None]

    app_metrics = {
        "cases_submitted": len(app_records),
        "answerable_cases_count": len(answerable),
        "answerable_correct_intent_count": sum(1 for r in answerable if r.get("correct_intent")),
        "safety_unanswerable_app_cases_count": len(safety),
        "collection_success_count": sum(1 for r in app_records if r["collection_success"]),
        "collection_failure_count": sum(1 for r in app_records if not r["collection_success"]),
        "answerable_automatic_raw_draft_ready_count": len(auto_raw_drafts),
        "answerable_automatic_correct_intent_draft_ready_count": len(auto_correct_drafts),
        "answerable_automatic_wrong_intent_draft_ready_count": len(auto_wrong_drafts),
        "answerable_automatic_wrong_intent_case_ids": [r["case_id"] for r in auto_wrong_drafts],
        "answerable_automatic_abstained_count": len(auto_abstained),
        "answerable_automatic_fallback_error_count": len(auto_fallback_errors),
        "answerable_automatic_fallback_case_ids": [r["case_id"] for r in auto_fallback_errors],
        "safety_expected_action_match_count": sum(1 for r in safety if r["action_matches_expected"] is True),
        "safety_unsafe_draft_count": len(safety_unsafe_drafts),
        "safety_unsafe_draft_case_ids": [r["case_id"] for r in safety_unsafe_drafts],
        "authority_check_passed_count": sum(1 for r in app_records if r["authority_check_passed"] is True),
        "source_verification_passed_count": sum(1 for r in app_records if r["source_verification_passed"] is True),
        "customer_tickets_inspected": len(app_records),
        "customer_no_auto_send_verified_all": bool(app_records) and all(r["customer_no_auto_send_observed"] is True for r in app_records),
        "strict_all_criteria_passed_count": sum(1 for r in app_records if r["is_success"]),
        "error_rate_app_cases": round(
            sum(1 for r in app_records if r["terminal_status"] in ("llm_unavailable", "unavailable", "timeout", "submission_error")) / max(len(app_records), 1),
            4,
        ),
        "latency_all_app_cases": compute_percentiles(app_latencies),
        "latency_answerable_cases": compute_percentiles(ans_latencies),
    }
    fix_metrics = {
        "cases_submitted": len(fixture_records),
        "encoder_provenance": fixture_records[0].get("encoder_provenance", "unknown") if fixture_records else "none",
        "collection_success_count": sum(1 for r in fixture_records if r["collection_success"]),
        "expiry_filtering_verified_count": sum(1 for r in fixture_records if r["slice"] == "expired_injected_boundary" and r["is_success"]),
        "conflict_detection_verified_count": sum(1 for r in fixture_records if r["slice"] == "conflict_injected_boundary" and r["is_success"]),
        "all_criteria_passed_count": sum(1 for r in fixture_records if r["is_success"]),
        "latency": compute_percentiles(fix_latencies),
    }
    return app_metrics, fix_metrics


def run_bounded_flash_lite_acceptance(
    *,
    output_base_dir: Path,
    worktree_root: Path = REPO_ROOT,
    root_repo: Path = DEFAULT_ROOT_REPO,
    env_path: Optional[Path] = None,
    max_requests: int = MAX_APPLICATION_LIVE_HTTP_REQUESTS,
    poll_timeout_seconds: float = 25.0,
    execute_live: bool = False,
    run_override_diagnostics: bool = True,
    long_timeout_seconds: float = 15.0,
) -> Dict[str, Any]:
    """Execute preflight + optional bounded live 24-call real-application Gemini 3.5 Flash-Lite acceptance."""
    configure_runtime_environment()
    resolved_env = env_path or (root_repo / ".env")
    cfg = load_flash_lite_private_config(resolved_env)
    secret_key = cfg["api_key"]
    model_dir = root_repo / "artifacts" / "models" / "trained" / "distilbert-supportiq"

    run_id = f"flash-lite-35-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    out_dir = Path(output_base_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=False)

    preflight = run_preflight(
        worktree_root=worktree_root,
        root_repo=root_repo,
        env_path=resolved_env,
        max_requests=max_requests,
    )
    preflight_path = out_dir / "dry_run_preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    oof_path = out_dir / "oof_lineage_audit.json"
    oof_path.write_text(json.dumps(preflight["oof_lineage_audit"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not execute_live:
        return {
            "run_id": run_id,
            "output_dir": str(out_dir),
            "executed_live": False,
            "preflight": preflight,
        }

    helper_collector = AcceptanceEvidenceCollector(
        mode="live",
        suite_path=worktree_root / "data/benchmarks/final_acceptance/cases.jsonl",
        manifest_path=worktree_root / "data/benchmarks/final_acceptance/suite_manifest.json",
        fixtures_path=worktree_root / "data/benchmarks/final_acceptance/injected_robustness_fixtures.json",
        paired_tasks_path=worktree_root / "data/benchmarks/final_acceptance/paired_agent_tasks.json",
        active_kb_path=worktree_root / "data/knowledge/approved_kb.v2.json",
        release_path=worktree_root / "apps/ai_service/kb-release.json",
        mock_orders_path=worktree_root / "data/knowledge/mock_orders.json",
    )

    guard = BudgetGuardedTransport(max_requests=max_requests)
    owner_url, default_passwords = resolve_database_url(str(root_repo / ".local" / "application.json"))
    schema = f"accept_fl35_{uuid.uuid4().hex[:10]}"
    root_engine = create_engine(owner_url, hide_parameters=True)
    app_engine = None
    schema_created = False

    phase1_app_records: List[Dict[str, Any]] = []
    phase1_fixture_records: List[Dict[str, Any]] = []
    phase2_override_records: List[Dict[str, Any]] = []
    phase2_skipped_budget: List[Dict[str, Any]] = []
    phase3_long_timeout_records: List[Dict[str, Any]] = []
    gateway_runtime_info: Dict[str, Any] = {}

    try:
        with root_engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        schema_created = True

        app_engine = create_engine(
            owner_url,
            connect_args={"options": f"-csearch_path={schema}"},
            hide_parameters=True,
        )
        database = Database(app_engine)
        database.create_schema()
        passwords = {
            role: default_passwords.get(role, uuid.uuid4().hex)
            for role in ("customer", "staff", "manager", "admin")
        }
        seed(database, passwords)

        with owned_isolated_ai_service(
            api_key=secret_key,
            model_name=FLASH_LITE_35_MODEL,
            model_dir=model_dir,
            budget_guard=guard,
        ) as gw:
            gateway_runtime_info = {
                "base_url": gw["base_url"],
                "health_ready": gw["health_ready"],
                "asset_versions": gw["asset_versions"],
                "configured_model": gw["configured_model"],
            }
            settings = BackendSettings(
                database_url_app=owner_url,
                database_url_owner=owner_url,
                allowed_origins=["http://testserver"],
                session_cookie_secure=False,
                ai_service_base_url=gw["base_url"],
                ai_service_analysis_timeout_ms=3000,
                ai_service_draft_timeout_ms=11000,
                job_poll_interval_ms=50,
            )

            with TestClient(create_backend_app(settings=settings, database=database, start_worker=True)) as customer, \
                 TestClient(create_backend_app(settings=settings, database=database, start_worker=False)) as staff:

                for cli, role in ((customer, "customer"), (staff, "staff")):
                    cli.headers["Origin"] = "http://testserver"
                    auth_resp = cli.post("/v1/sessions", json={"login_name": f"{role}-1", "password": passwords[role]})
                    if auth_resp.status_code != 201:
                        raise RuntimeError(f"Authentication failed for synthetic {role}: {auth_resp.status_code}")

                cases_by_id = {c["id"]: c for c in helper_collector.cases}

                # Phase 1: All 24 frozen cases in primary automatic application mode
                for c in helper_collector.cases:
                    if c.get("fixture_boundary") == "injected_synthetic":
                        phase1_fixture_records.append(_evaluate_injected_fixture_case(c, helper_collector))
                        continue

                    t0 = time.perf_counter()
                    payload = {"message": c["query"]}
                    if c.get("order_id"):
                        payload["order_id"] = c["order_id"]
                    t_resp = customer.post(
                        "/v1/shop/tickets",
                        headers={"Idempotency-Key": str(uuid.uuid4())},
                        json=payload,
                    )
                    if t_resp.status_code != 201:
                        wall_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                        phase1_app_records.append(
                            {
                                "phase": "primary_automatic_application",
                                "case_id": c["id"],
                                "slice": c["slice"],
                                "fixture_boundary": c["fixture_boundary"],
                                "component_evidence": "application_postgresql_gateway",
                                "expected_intent": c["intent"],
                                "expected_action": c["expected_action"],
                                "ticket_id": None,
                                "submit_to_terminal_latency_ms": wall_ms,
                                "terminal_status": "submission_error",
                                "collection_success": False,
                                "action_matches_expected": False,
                                "reasons_match_expected": False,
                                "authority_check_passed": False,
                                "source_verification_passed": False,
                                "customer_no_auto_send_observed": False,
                                "correct_intent": False,
                                "is_success": False,
                            }
                        )
                        continue

                    t_id = t_resp.json()["ticket_id"]
                    reached, suggestion_data = _poll_ticket_suggestion(
                        staff, t_id, poll_timeout_seconds=poll_timeout_seconds
                    )
                    wall_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    cust_obs = _observe_customer_ticket(customer, t_id)

                    exec_ctx: Dict[str, Any] = {}
                    exec_as_of: Optional[str] = None
                    with database.transaction() as db_sess:
                        t_obj = db_sess.get(Ticket, t_id)
                        if t_obj and t_obj.current_suggestion_id:
                            s_obj = db_sess.get(Suggestion, t_obj.current_suggestion_id)
                            if s_obj and s_obj.request_payload:
                                exec_ctx = dict(s_obj.request_payload.get("order_context") or {})
                                exec_as_of = s_obj.request_payload.get("as_of")

                    phase1_app_records.append(
                        _build_record_from_suggestion(
                            phase="primary_automatic_application",
                            case=c,
                            ticket_id=t_id,
                            wall_latency_ms=wall_ms,
                            reached_terminal=reached,
                            suggestion_data=suggestion_data,
                            cust_obs=cust_obs,
                            executed_order_context=exec_ctx,
                            executed_as_of=exec_as_of,
                            helper_collector=helper_collector,
                            secret_key=secret_key,
                        )
                    )

                # Phase 2: Separately labeled staff intent-override diagnostic on missed/failed answerable cases
                if run_override_diagnostics:
                    needs_override = [
                        r for r in phase1_app_records
                        if r["slice"] == "product_12_answerable"
                        and not (r["terminal_status"] == "draft_ready" and r["correct_intent"])
                    ]
                    # Prioritize abstained/failed before wrong-intent draft, then wrong-intent draft
                    needs_override.sort(key=lambda r: (0 if r["terminal_status"] != "draft_ready" else 1, r["case_id"]))
                    for r in needs_override:
                        case = cases_by_id[r["case_id"]]
                        t_id = r.get("ticket_id")
                        if not t_id:
                            phase2_skipped_budget.append({"case_id": case["id"], "reason": "missing_ticket_id"})
                            continue
                        if guard.requests_attempted >= guard.max_requests:
                            phase2_skipped_budget.append(
                                {
                                    "case_id": case["id"],
                                    "reason": f"budget_cap_{guard.max_requests}_reached_before_dispatch",
                                }
                            )
                            continue

                        t0 = time.perf_counter()
                        ov_resp = staff.post(
                            f"/v1/console/tickets/{t_id}/suggestions",
                            headers={"Idempotency-Key": str(uuid.uuid4())},
                            json={"intent_override": case["intent"]},
                        )
                        if ov_resp.status_code != 202:
                            phase2_skipped_budget.append(
                                {"case_id": case["id"], "reason": f"override_http_{ov_resp.status_code}"}
                            )
                            continue
                        new_sid = ov_resp.json().get("suggestion_id")
                        reached, suggestion_data = _poll_ticket_suggestion(
                            staff,
                            t_id,
                            poll_timeout_seconds=poll_timeout_seconds,
                            expected_suggestion_id=new_sid,
                        )
                        wall_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                        cust_obs = _observe_customer_ticket(customer, t_id)

                        exec_ctx = {}
                        exec_as_of = None
                        with database.transaction() as db_sess:
                            t_obj = db_sess.get(Ticket, t_id)
                            if t_obj and t_obj.current_suggestion_id:
                                s_obj = db_sess.get(Suggestion, t_obj.current_suggestion_id)
                                if s_obj and s_obj.request_payload:
                                    exec_ctx = dict(s_obj.request_payload.get("order_context") or {})
                                    exec_as_of = s_obj.request_payload.get("as_of")

                        phase2_override_records.append(
                            _build_record_from_suggestion(
                                phase="oracle_staff_override_application_diagnostic",
                                case=case,
                                ticket_id=t_id,
                                wall_latency_ms=wall_ms,
                                reached_terminal=reached,
                                suggestion_data=suggestion_data,
                                cust_obs=cust_obs,
                                executed_order_context=exec_ctx,
                                executed_as_of=exec_as_of,
                                helper_collector=helper_collector,
                                secret_key=secret_key,
                            )
                        )

                # Phase 3: Optional separately labeled long-timeout component diagnostic ONLY if any 5s/10s timeout happened
                timed_out_cases = [
                    r for r in (phase1_app_records + phase2_override_records)
                    if r["slice"] == "product_12_answerable" and r.get("failure_code") == "llm_timeout"
                ]
                seen_timeout_ids = set()
                if timed_out_cases and guard.requests_attempted < guard.max_requests:
                    from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
                    from apps.core_backend.retrieval.adapter import RetrievalAdapter

                    release = json.loads((worktree_root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8"))
                    allowed = {(d["document_id"], d["version"]) for d in release["documents"]}
                    comp_retriever = RetrievalAdapter(
                        kb_path=str(worktree_root / "data/knowledge/approved_kb.v2.json"),
                        allowed_document_versions=allowed,
                    )
                    comp_client = GeminiDraftClient(
                        api_key=secret_key,
                        model=FLASH_LITE_35_MODEL,
                        http_client=httpx.Client(transport=_SharedGuardTransportAdapter(guard), trust_env=False, follow_redirects=False),
                    )
                    try:
                        for tr in timed_out_cases:
                            cid = tr["case_id"]
                            if cid in seen_timeout_ids or guard.requests_attempted >= guard.max_requests:
                                continue
                            seen_timeout_ids.add(cid)
                            case = cases_by_id[cid]
                            as_of_dt = datetime.fromisoformat(case["as_of"].replace("Z", "+00:00"))
                            ret = comp_retriever.retrieve(case["query"], case["intent"], role="agent", current_time=as_of_dt)
                            evidence = ret.get("evidence", [])
                            t0 = time.perf_counter()
                            try:
                                gen = comp_client.generate(
                                    case["query"],
                                    case["intent"],
                                    evidence,
                                    business_context=case.get("order_context") or {},
                                    timeout_seconds=long_timeout_seconds,
                                )
                                phase3_long_timeout_records.append(
                                    {
                                        "phase": "long_timeout_component_diagnostic",
                                        "case_id": cid,
                                        "expected_intent": case["intent"],
                                        "timeout_seconds": long_timeout_seconds,
                                        "status": "draft_ready",
                                        "wall_elapsed_seconds": round(time.perf_counter() - t0, 4),
                                        "reported_model": gen.get("model"),
                                        "reported_model_version": gen.get("model_version"),
                                        "draft_body": sanitize_text(gen.get("body"), secret_key),
                                        "citations": gen.get("citations", []),
                                        "usage": gen.get("usage", {}),
                                        "attempts": gen.get("attempts", []),
                                    }
                                )
                            except LLMError as exc:
                                phase3_long_timeout_records.append(
                                    {
                                        "phase": "long_timeout_component_diagnostic",
                                        "case_id": cid,
                                        "expected_intent": case["intent"],
                                        "timeout_seconds": long_timeout_seconds,
                                        "status": exc.code,
                                        "wall_elapsed_seconds": round(time.perf_counter() - t0, 4),
                                        "usage": exc.usage,
                                        "attempts": exc.attempts,
                                    }
                                )
                    finally:
                        comp_client.close()
    finally:
        guard.close()
        if app_engine is not None:
            try:
                app_engine.dispose()
            except Exception:
                pass
        schema_cleanup_info = _drop_temporary_postgres_schema(
            root_engine, schema, schema_created=schema_created
        )
        root_engine.dispose()

    app_metrics, fixture_metrics = _summarize_phase1_metrics(phase1_app_records, phase1_fixture_records)
    phase2_latencies = [float(r["submit_to_terminal_latency_ms"]) for r in phase2_override_records if r.get("submit_to_terminal_latency_ms") is not None]
    phase2_drafts = [r for r in phase2_override_records if r["terminal_status"] == "draft_ready" and r["source_verification_passed"]]

    all_attempts: List[Dict[str, Any]] = []
    for rec in phase1_app_records + phase2_override_records:
        for att in rec.get("attempts") or []:
            all_attempts.append({"case_id": rec["case_id"], "phase": rec["phase"], **att})
    for rec in phase3_long_timeout_records:
        for att in rec.get("attempts") or []:
            all_attempts.append({"case_id": rec["case_id"], "phase": rec["phase"], **att})

    tokens_and_cost = summarize_flash_lite_tokens_and_cost(all_attempts, configured_model=FLASH_LITE_35_MODEL)
    transport_calls = [
        {**rec, "error": sanitize_text(rec.get("error"), secret_key)} if "error" in rec else rec
        for rec in guard.records
    ]

    budget_accounting = {
        "authorized_max_http_requests": max_requests,
        "actual_http_requests_made": guard.requests_attempted,
        "remaining_http_requests": max(0, max_requests - guard.requests_attempted),
        "rejected_before_network_count": guard.rejected_before_network_count,
        "budget_enforced_within_cap": guard.requests_attempted <= max_requests,
        "transport_retries_configured": guard._retries_configured,
        "allowed_egress_host": ALLOWED_GEMINI_HOST,
    }

    combined_answerable_correct_drafts = sorted(
        {r["case_id"] for r in phase1_app_records if r["slice"] == "product_12_answerable" and r["terminal_status"] == "draft_ready" and r["correct_intent"]}
        | {r["case_id"] for r in phase2_drafts}
    )

    report = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": get_git_commit_hash(),
        "isolated_runtime": {
            **gateway_runtime_info,
            **schema_cleanup_info,
            "root_ports_8080_8002_untouched": True,
        },
        "budget_accounting": budget_accounting,
        "phase1_primary_automatic_application": app_metrics,
        "phase1_injected_component_boundaries": fixture_metrics,
        "phase2_oracle_staff_override_diagnostic": {
            "cases_attempted": len(phase2_override_records),
            "draft_ready_and_source_verified_count": len(phase2_drafts),
            "fallback_or_failed_count": len(phase2_override_records) - len(phase2_drafts),
            "no_auto_send_verified_all": bool(phase2_override_records) and all(r["customer_no_auto_send_observed"] is True for r in phase2_override_records),
            "skipped_or_blocked_cases": phase2_skipped_budget,
            "latency": compute_percentiles(phase2_latencies),
        },
        "phase3_long_timeout_component_diagnostic": {
            "executed": bool(phase3_long_timeout_records),
            "timeout_seconds": long_timeout_seconds if phase3_long_timeout_records else None,
            "cases": phase3_long_timeout_records,
            "note": (
                "Executed separately ONLY for cases that timed out under primary 5s/10s deadlines."
                if phase3_long_timeout_records
                else "Not needed: zero llm_timeout failures under primary 5s/10s deadlines."
            ),
        },
        "combined_unique_answerable_correct_intent_drafts": {
            "automatic_only_count": app_metrics["answerable_automatic_correct_intent_draft_ready_count"],
            "automatic_plus_staff_override_count": len(combined_answerable_correct_drafts),
            "case_ids": combined_answerable_correct_drafts,
            "note": "Combined count explicitly separates staff-assisted override coverage from primary automatic classifier coverage.",
        },
        "tokens_and_cost": tokens_and_cost,
        "transport_calls": transport_calls,
        "phase1_application_records": phase1_app_records,
        "phase1_injected_fixture_records": phase1_fixture_records,
        "phase2_override_records": phase2_override_records,
        "oof_lineage_summary": preflight["oof_lineage_audit"],
    }

    report_hashes = _persist_run_outputs(
        out_dir=out_dir,
        report=report,
        phase1_app_records=phase1_app_records,
        phase1_fixture_records=phase1_fixture_records,
        phase2_override_records=phase2_override_records,
        secret_key=secret_key,
    )
    return {
        "run_id": run_id,
        "output_dir": str(out_dir),
        "executed_live": True,
        "report": report,
        "report_hashes": report_hashes,
    }


def render_flash_lite_markdown_report(report: Dict[str, Any]) -> str:
    """Render a concise human-readable markdown summary of the bounded Flash-Lite 3.5 run."""
    b = report["budget_accounting"]
    p1 = report["phase1_primary_automatic_application"]
    fix = report["phase1_injected_component_boundaries"]
    p2 = report["phase2_oracle_staff_override_diagnostic"]
    p3 = report["phase3_long_timeout_component_diagnostic"]
    comb = report["combined_unique_answerable_correct_intent_drafts"]
    tc = report["tokens_and_cost"]
    oof = report["oof_lineage_summary"]["distilbert_oof"]
    srv = report["oof_lineage_summary"]["serving_training_report_linkage"]

    ir = report.get("isolated_runtime") or {}
    dropped_flag = ir.get("postgres_schema_dropped_cleanly")
    if dropped_flag is True:
        schema_drop_desc = "dropped cleanly"
    elif dropped_flag is False:
        err_cat = ir.get("postgres_schema_drop_error_category") or "unknown"
        schema_drop_desc = f"cleanup FAILED (error_category={err_cat})"
    else:
        drop_status = ir.get("postgres_schema_drop_status") or "unknown"
        schema_drop_desc = f"cleanup status={drop_status}"

    thought_status = tc.get("thought_tokens_measurement_status")
    thought_disp = tc.get("observed_thought_tokens")
    if thought_disp is None or thought_status == "omitted_all_attempts":
        thought_line = f"unmeasured / omitted in all `{tc['total_attempts_counted']}` attempts (not measured zero)"
    else:
        thought_line = f"`{thought_disp}` (reported in `{tc['attempts_with_thought_tokens_field']}/{tc['total_attempts_counted']}` attempts; status=`{thought_status or 'measured'}`)"

    lines = [
        f"# Task C Bounded Application Acceptance Report (`{report['run_id']}`)",
        "",
        f"- **Generated At:** `{report['generated_at']}`",
        f"- **Git Commit:** `{report['git_commit']}`",
        f"- **Configured Model:** `{ir.get('configured_model')}`",
        f"- **PostgreSQL Isolation:** Temporary schema `{ir.get('postgres_schema')}` ({schema_drop_desc}; root ports `8080/8002` untouched)",
        "",
        "## 1. Live LLM Budget Accounting",
        f"- **Authorized Max HTTP Requests:** `{b['authorized_max_http_requests']}`",
        f"- **Actual HTTP Requests Made:** `{b['actual_http_requests_made']}`",
        f"- **Rejected Before Network:** `{b['rejected_before_network_count']}`",
        f"- **Transport Retries Configured:** `{b['transport_retries_configured']}`",
        f"- **Budget Enforced Within Cap:** `{b['budget_enforced_within_cap']}`",
        "",
        "## 2. Phase 1: Primary Automatic Real-Application Results",
        f"- **Frozen Cases Submitted (Gateway + PG):** `{p1['cases_submitted']}` (`12` answerable + `8` active-KB safety/escalation/unsupported/OOD; plus `{fix['cases_submitted']}` injected component boundary fixtures)",
        f"- **Answerable Cases Correct-Intent:** `{p1['answerable_correct_intent_count']}/12`",
        f"- **Answerable Automatic Correct-Intent `draft_ready`:** `{p1['answerable_automatic_correct_intent_draft_ready_count']}/12`",
        f"- **Answerable Wrong-Intent Drafts:** `{p1['answerable_automatic_wrong_intent_draft_ready_count']}` (`{p1['answerable_automatic_wrong_intent_case_ids']}`)",
        f"- **Answerable Abstained:** `{p1['answerable_automatic_abstained_count']}`",
        f"- **Answerable Fallback / Unavailable Errors:** `{p1['answerable_automatic_fallback_error_count']}` (`{p1['answerable_automatic_fallback_case_ids']}`)",
        f"- **Safety Unsafe Drafts:** `{p1['safety_unsafe_draft_count']}` (`{p1['safety_unsafe_draft_case_ids']}`)",
        f"- **Customer Auto-Send Blocking (`no_auto_send`):** `{p1['customer_no_auto_send_verified_all']}`",
        f"- **Source Verification Passed:** `{p1['source_verification_passed_count']}/{p1['cases_submitted']}`",
        f"- **Error Rate (`llm_unavailable`/timeout):** `{p1['error_rate_app_cases']}`",
        f"- **End-to-End Wall Latency (ms):** all `p50={p1['latency_all_app_cases']['p50_interpolated_ms']}` (nearest `{p1['latency_all_app_cases']['p50_nearest_rank_ms']}`), `p95={p1['latency_all_app_cases']['p95_interpolated_ms']}` (nearest `{p1['latency_all_app_cases']['p95_nearest_rank_ms']}`) | answerable `p50={p1['latency_answerable_cases']['p50_interpolated_ms']}`, `p95={p1['latency_answerable_cases']['p95_interpolated_ms']}`",
        f"- **Injected Component Fixtures (`final-case-21..24`):** `{fix['all_criteria_passed_count']}/{fix['cases_submitted']}` passed (`expiry={fix['expiry_filtering_verified_count']}/2`, `conflict={fix['conflict_detection_verified_count']}/2`, encoder=`{fix['encoder_provenance']}`)",
        "",
        "## 3. Phase 2: Separately Labeled Staff Intent-Override Diagnostic",
        f"- **Override Cases Attempted:** `{p2['cases_attempted']}`",
        f"- **Override `draft_ready` & Source-Verified:** `{p2['draft_ready_and_source_verified_count']}`",
        f"- **Fallback / Failed:** `{p2['fallback_or_failed_count']}`",
        f"- **Combined Unique Answerable Correct-Intent Drafts (Auto + Staff Override):** `{comb['automatic_plus_staff_override_count']}/12` (`{comb['case_ids']}`)",
        "",
        "## 4. Phase 3: Long-Timeout Component Diagnostic",
        f"- **Executed:** `{p3['executed']}` — {p3['note']}",
        "",
        "## 5. Tokens & Cost Accounting (Strict Non-Fabrication)",
        f"- **Attempts Counted:** `{tc['total_attempts_counted']}` (missing usage: `{tc['attempts_missing_usage']}`, with `thoughtsTokenCount`: `{tc['attempts_with_thought_tokens_field']}` / omitted: `{tc.get('attempts_with_thought_tokens_omitted', tc['total_attempts_counted'] - tc['attempts_with_thought_tokens_field'])}`)",
        f"- **Observed Prompt / Candidate Tokens:** `{tc['observed_prompt_tokens']}` / `{tc['observed_candidate_tokens']}` (thoughts: {thought_line})",
        f"- **Complete Cost Known / Invoice Verified:** `{tc['complete_cost_known']}` / `{tc['invoice_verified']}` (`cost_status={tc['cost_status']}`, `complete_billed_cost_usd={tc['complete_billed_cost_usd']}`)",
        f"- **Conditional Observed List-Price USD ($0.30/1M in, $2.50/1M out; candidate-only when thoughts omitted):** `${tc['conditional_observed_list_price_usd']}`",
        "",
        "## 6. Stored 10-Fold OOF Verification (Zero Retraining)",
        f"- **DistilBERT OOF Records (`{oof['oof_path']}`):** `{oof['total_rows']}` rows, `{oof['n_folds']}` folds, `{oof['n_labels']}` intents, mean fold macro-F1 `{oof['macro_f1_mean']:.6f}` (`std_ddof1={oof['macro_f1_std_ddof1']:.6f}`), global OOF macro-F1 `{oof['oof_macro_f1']:.6f}`",
        f"- **Serving `training_report.json` Cross-Check:** `matches_oof_macro_f1_mean_within_1e12={srv.get('matches_oof_macro_f1_mean_within_1e12')}`, `matches_all_10_fold_metrics_within_1e12={srv.get('matches_all_10_fold_metrics_within_1e12')}`, `train_sample_ids_sha256_match={srv.get('train_sample_ids_sha256_match')}`",
    ]
    return "\n".join(lines) + "\n"


def _persist_run_outputs(
    out_dir: Path,
    report: Dict[str, Any],
    phase1_app_records: List[Dict[str, Any]],
    phase1_fixture_records: List[Dict[str, Any]],
    phase2_override_records: List[Dict[str, Any]],
    secret_key: str,
) -> Dict[str, str]:
    raw_report = json.dumps(report, indent=2, ensure_ascii=False)
    if secret_key and secret_key in raw_report:
        raise RuntimeError("Refusing to persist report: secret API key detected in serialized output")

    md_text = render_flash_lite_markdown_report(report)
    if secret_key and secret_key in md_text:
        raise RuntimeError("Refusing to persist markdown report: secret API key detected")

    (out_dir / "flash_lite_acceptance_report.json").write_text(raw_report + "\n", encoding="utf-8")
    (out_dir / "FLASH_LITE_ACCEPTANCE_REPORT.md").write_text(md_text, encoding="utf-8")

    (out_dir / "phase1_application_records.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in (phase1_app_records + phase1_fixture_records)) + "\n",
        encoding="utf-8",
    )
    (out_dir / "phase2_override_records.jsonl").write_text(
        ("\n".join(json.dumps(r, ensure_ascii=False) for r in phase2_override_records) + "\n")
        if phase2_override_records
        else "",
        encoding="utf-8",
    )

    report_hashes = {
        p.name: compute_sha256(p)
        for p in sorted(out_dir.iterdir())
        if p.is_file() and p.name != "report_hashes.json"
    }
    (out_dir / "report_hashes.json").write_text(json.dumps(report_hashes, indent=2) + "\n", encoding="utf-8")
    return report_hashes
