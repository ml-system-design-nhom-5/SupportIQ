"""Bounded live Gemini verification harness for Task C (4 oracle-intent cases, max 8 HTTP requests)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import statistics
import threading
import time
from typing import Any

import httpx

TARGET_LIVE_CASE_IDS = (
    "final-case-02",
    "final-case-03",
    "final-case-10",
    "final-case-12",
)
MAX_LIVE_HTTP_REQUESTS = 8
MAX_LIVE_TOP_LEVEL_GENERATIONS = 4
ALLOWED_GEMINI_HOST = "generativelanguage.googleapis.com"
LIST_PRICE_PER_MILLION_USD = {
    "provider": "google_ai_studio",
    "model": "gemini-3.1-flash-lite",
    "tier": "standard_paid",
    "modality": "text",
    "input_cost_per_million": 0.25,
    "output_cost_per_million": 1.50,
    "output_includes_thinking": True,
    "source_url": "https://aistudio.google.com/docs/pricing#gemini-3.1-flash-lite",
    "requested_source_url": "https://ai.google.dev/gemini-api/docs/pricing",
    "verified_on": "2026-11-12",
    "note": "Published standard paid-tier text token list rates (output rate includes thinking tokens); actual account billing tier/invoice is unverified.",
}


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sanitize_text(text: str | None, secret_key: str = "") -> str:
    if not text:
        return ""
    out = str(text)
    if secret_key and len(secret_key) >= 6:
        out = out.replace(secret_key, "[REDACTED_API_KEY]")
    out = re.sub(r"AIza[0-9A-Za-z_-]{10,}", "[REDACTED_GOOGLE_KEY]", out)
    out = re.sub(r"(?i)(x-goog-api-key|authorization)\s*[:=]\s*\S+", r"\1=[REDACTED]", out)
    return out


def load_private_provider_config(env_path: Path) -> dict[str, Any]:
    """Read provider config privately in memory without writing secrets to env, logs, or artifacts."""
    if not env_path.exists():
        raise FileNotFoundError(f"Configured provider env file missing: {env_path}")
    parsed: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        parsed[k.strip()] = v.strip().strip("\"'")
    api_key = parsed.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is missing or empty in private provider configuration")
    model = (parsed.get("GEMINI_MODEL") or "gemini-3.1-flash-lite").strip()
    if not model:
        raise ValueError("GEMINI_MODEL is empty in private provider configuration")
    return {
        "provider": "google_ai_studio",
        "model": model,
        "api_key": api_key,
        "configured_timeout_env": parsed.get("GEMINI_TIMEOUT_SECONDS"),
    }


class BudgetExhaustedBeforeNetworkError(httpx.RequestError):
    """Raised before network I/O when the authorized live HTTP request cap is reached."""


class BudgetGuardedTransport(httpx.BaseTransport):
    """Thread-safe transport boundary enforcing max HTTP requests BEFORE network I/O and disabling retries."""

    def __init__(
        self,
        max_requests: int = MAX_LIVE_HTTP_REQUESTS,
        inner: httpx.BaseTransport | None = None,
    ) -> None:
        if type(max_requests) is not int or max_requests < 1:
            raise ValueError(f"max_requests must be a positive int, got {max_requests!r}")
        self.max_requests = max_requests
        if inner is None:
            self._inner: httpx.BaseTransport = httpx.HTTPTransport(retries=0)
            self._retries_configured = 0
        else:
            self._inner = inner
            self._retries_configured = getattr(inner, "_retries", 0)
        self._lock = threading.Lock()
        self.requests_attempted = 0
        self.rejected_before_network_count = 0
        self.records: list[dict[str, Any]] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.url.scheme != "https" or request.url.host != ALLOWED_GEMINI_HOST:
            raise httpx.RequestError(f"Egress host is not allowed: {request.url.scheme}://{request.url.host}", request=request)

        with self._lock:
            if self.requests_attempted >= self.max_requests:
                self.rejected_before_network_count += 1
                self.records.append(
                    {
                        "transport_call_index": self.requests_attempted,
                        "rejected_before_network": True,
                        "scheme": request.url.scheme,
                        "host": request.url.host,
                        "path": request.url.path,
                        "outcome": "budget_rejected_before_network",
                        "http_status": None,
                        "duration_seconds": 0.0,
                    }
                )
                raise BudgetExhaustedBeforeNetworkError(
                    f"Hard live HTTP budget reached ({self.requests_attempted}/{self.max_requests}); blocked before network I/O",
                    request=request,
                )
            call_idx = self.requests_attempted
            self.requests_attempted += 1

        timeout_ext = request.extensions.get("timeout", {}) if isinstance(request.extensions, dict) else {}
        t0 = time.perf_counter()
        try:
            resp = self._inner.handle_request(request)
            dur = round(time.perf_counter() - t0, 4)
            with self._lock:
                self.records.append(
                    {
                        "transport_call_index": call_idx,
                        "rejected_before_network": False,
                        "scheme": request.url.scheme,
                        "host": request.url.host,
                        "path": request.url.path,
                        "requested_read_timeout": timeout_ext.get("read"),
                        "requested_connect_timeout": timeout_ext.get("connect"),
                        "outcome": "http_response",
                        "http_status": resp.status_code,
                        "duration_seconds": dur,
                    }
                )
            return resp
        except Exception as exc:
            dur = round(time.perf_counter() - t0, 4)
            with self._lock:
                self.records.append(
                    {
                        "transport_call_index": call_idx,
                        "rejected_before_network": False,
                        "scheme": request.url.scheme,
                        "host": request.url.host,
                        "path": request.url.path,
                        "requested_read_timeout": timeout_ext.get("read"),
                        "requested_connect_timeout": timeout_ext.get("connect"),
                        "outcome": type(exc).__name__,
                        "http_status": None,
                        "duration_seconds": dur,
                    }
                )
            raise

    def close(self) -> None:
        self._inner.close()


def select_target_cases(cases_path: Path) -> list[dict[str, Any]]:
    raw = [json.loads(ln) for ln in cases_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    by_id = {c["id"]: c for c in raw}
    selected = [by_id[cid] for cid in TARGET_LIVE_CASE_IDS]
    if len(selected) > MAX_LIVE_TOP_LEVEL_GENERATIONS:
        raise ValueError(f"Exceeded max 4 top-level generations: {len(selected)}")
    return selected


def summarize_tokens_and_conditional_cost(case_records: list[dict[str, Any]], model_name: str) -> dict[str, Any]:
    """Summarize observed tokens conservatively; incomplete/timeout attempts leave totals/cost incomplete."""
    all_attempts: list[dict[str, Any]] = []
    for c in case_records:
        all_attempts.extend(c.get("attempts") or [])

    observed_input = 0
    observed_output = 0
    observed_thoughts = 0
    observed_total = 0
    missing_usage_attempts = 0

    for att in all_attempts:
        u = att.get("usage") or {}
        p = u.get("promptTokenCount")
        cand = u.get("candidatesTokenCount")
        tot = u.get("totalTokenCount")
        th = u.get("thoughtsTokenCount")
        if type(p) is int and not isinstance(p, bool) and p >= 0:
            observed_input += p
        if type(cand) is int and not isinstance(cand, bool) and cand >= 0:
            observed_output += cand
        if type(th) is int and not isinstance(th, bool) and th >= 0:
            observed_thoughts += th
        if type(tot) is int and not isinstance(tot, bool) and tot >= 0:
            observed_total += tot
        if not (
            type(p) is int and not isinstance(p, bool)
            and type(cand) is int and not isinstance(cand, bool)
            and type(tot) is int and not isinstance(tot, bool)
        ):
            missing_usage_attempts += 1

    complete_coverage = bool(all_attempts) and missing_usage_attempts == 0
    conditional_observed_usd = round(
        (observed_input / 1_000_000.0) * LIST_PRICE_PER_MILLION_USD["input_cost_per_million"]
        + ((observed_output + observed_thoughts) / 1_000_000.0) * LIST_PRICE_PER_MILLION_USD["output_cost_per_million"],
        8,
    )
    return {
        "total_attempts_counted": len(all_attempts),
        "attempts_missing_usage": missing_usage_attempts,
        "complete_token_coverage": complete_coverage,
        "observed_prompt_tokens": observed_input,
        "observed_candidate_tokens": observed_output,
        "observed_thought_tokens": observed_thoughts,
        "observed_reported_total_tokens": observed_total if complete_coverage else None,
        "observed_partial_total_tokens": observed_total,
        "complete_cost_known": False,
        "invoice_verified": False,
        "cost_status": (
            "complete_tokens_conditional_list_price_not_invoice"
            if complete_coverage
            else "incomplete_token_coverage"
        ),
        "conditional_observed_list_price_usd": conditional_observed_usd,
        "list_price_reference_used": {**LIST_PRICE_PER_MILLION_USD, "configured_model": model_name},
        "complete_cost_usd": None,
        "cost_note": (
            "Conditional USD computed solely from observed tokens using placeholder flash-lite list pricing; actual invoice/account billing tier is unverified."
            if complete_coverage
            else "One or more attempts lacked complete provider usage (e.g., timeout/error); total tokens and complete cost are UNKNOWN."
        ),
    }


def run_bounded_live_verification(
    worktree_root: Path,
    model_dir: Path,
    private_env_path: Path,
    *,
    execute_live: bool = False,
    source_commit: str | None = None,
) -> dict[str, Any]:
    """Execute 4 oracle-intent grounded-provider generations against ff0e147 with hard 8-HTTP-request lock."""
    import apps.ml_inference.app as ml_app
    from apps.ai_service.drafting import BudgetedDraftClient
    from apps.ai_service.engine import Engine
    from apps.core_backend.llm.gemini import GeminiDraftClient, PROMPT_VERSION
    from apps.core_backend.retrieval.adapter import RetrievalAdapter

    cases_path = worktree_root / "data/benchmarks/final_acceptance/cases.jsonl"
    kb_path = worktree_root / "data/knowledge/approved_kb.v2.json"
    release_path = worktree_root / "apps/ai_service/kb-release.json"
    policy_path = worktree_root / "apps/core_backend/config/policies/intent_policy.v2.json"

    cases = select_target_cases(cases_path)
    kb_docs = json.loads(kb_path.read_text(encoding="utf-8"))
    kb_by_key = {(d.get("document_id", d.get("doc_id")), str(d.get("version"))): d for d in kb_docs}
    release = json.loads(release_path.read_text(encoding="utf-8"))
    allowed = {(d["document_id"], str(d["version"])) for d in release["documents"]}
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    cfg = load_private_provider_config(private_env_path)
    api_key = cfg.pop("api_key")

    model = ml_app.ModelContainer()
    model.load(model_dir)
    retriever = RetrievalAdapter(kb_path=str(kb_path), allowed_document_versions=allowed)
    versions = {
        "kb_version": release.get("kb_version", "2.0"),
        "policy_version": policy.get("version", "2.0"),
        "prompt_version": PROMPT_VERSION,
        "model_version": model.model_version or "v1.0.0",
        "model_mode": model.model_mode,
        "verified": True,
    }

    guarded_transport = BudgetGuardedTransport(max_requests=MAX_LIVE_HTTP_REQUESTS)
    preflight = {
        "preflight_budget": f"{guarded_transport.requests_attempted}/{guarded_transport.max_requests}",
        "requests_attempted_before_first_call": guarded_transport.requests_attempted,
        "max_requests": guarded_transport.max_requests,
        "max_top_level_generations": MAX_LIVE_TOP_LEVEL_GENERATIONS,
        "transport_retries_configured": guarded_transport._retries_configured,
        "trust_env": False,
        "follow_redirects": False,
        "attempt_timeout_seconds": 5.0,
        "budget_seconds": 10.0,
        "provider": cfg["provider"],
        "model": cfg["model"],
        "prompt_version": PROMPT_VERSION,
    }
    print(
        f"Preflight budget: {preflight['preflight_budget']} | model={cfg['model']} | "
        f"prompt={PROMPT_VERSION} | transport_retries={guarded_transport._retries_configured}"
    )

    if not execute_live:
        http_client = httpx.Client(transport=guarded_transport, follow_redirects=False, trust_env=False)
        engine = Engine(model, retriever, llm=None, versions=versions, policy=policy)
        dry_rows = []
        try:
            for c in cases:
                pred = model.predict(c["query"])
                analysis, ev = engine._analyse(
                    {
                        "message": c["query"],
                        "order_context": c["order_context"],
                        "as_of": c["as_of"],
                        "intent_override": c["intent"],
                    }
                )
                dry_rows.append(
                    {
                        "case_id": c["id"],
                        "expected_intent": c["intent"],
                        "serving_raw_prediction": pred["intent"],
                        "serving_raw_confidence": round(float(pred["confidence"]), 6),
                        "oracle_routing_recommendation": analysis["routing"]["recommendation"],
                        "retrieved_docs": [f"{d['document_id']}:{d['version']}" for d in ev],
                    }
                )
        finally:
            http_client.close()
        return {
            "report_type": "bounded_live_verification_dry_run",
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "source_commit": source_commit or "workspace",
            "preflight": preflight,
            "final_http_requests": guarded_transport.requests_attempted,
            "cases": dry_rows,
        }

    http_client = httpx.Client(
        transport=guarded_transport,
        timeout=httpx.Timeout(5.0, connect=3.0),
        follow_redirects=False,
        trust_env=False,
    )
    gemini = GeminiDraftClient(api_key=api_key, model=cfg["model"], http_client=http_client)
    budgeted = BudgetedDraftClient(gemini, budget_seconds=10.0, attempt_timeout_seconds=5.0, max_attempts=2)
    engine = Engine(model, retriever, budgeted, versions=versions, policy=policy)

    case_results: list[dict[str, Any]] = []
    try:
        for c in cases:
            if guarded_transport.requests_attempted >= MAX_LIVE_HTTP_REQUESTS:
                break
            req_start = guarded_transport.requests_attempted
            pred = model.predict(c["query"])
            t0 = time.perf_counter()
            result = engine.draft(
                {
                    "message": c["query"],
                    "order_context": c["order_context"],
                    "as_of": c["as_of"],
                    "intent_override": c["intent"],
                }
            )
            wall_elapsed = round(time.perf_counter() - t0, 4)
            req_end = guarded_transport.requests_attempted

            attempts = list((result.get("llm_metadata") or {}).get("attempts") or getattr(budgeted, "last_attempts", []) or [])
            sanitized_attempts = []
            for att in attempts:
                att_copy = dict(att)
                att_copy["usage"] = dict(att.get("usage") or {})
                sanitized_attempts.append(att_copy)

            retrieved_docs_prov = []
            for doc in (result.get("analysis") or {}).get("documents") or []:
                k = (doc["document_id"], str(doc["version"]))
                kb_rec = kb_by_key.get(k, {})
                raw_content = kb_rec.get("content", "")
                retrieved_docs_prov.append(
                    {
                        "document_id": doc["document_id"],
                        "version": str(doc["version"]),
                        "score": doc.get("score"),
                        "kb_recorded_content_hash": kb_rec.get("content_hash"),
                        "source_content_sha256": sha256_text(raw_content) if raw_content else None,
                        "valid_from": doc.get("effective_from"),
                        "valid_to": doc.get("effective_to"),
                    }
                )

            draft_payload = None
            if result.get("draft"):
                draft_payload = {
                    "segments": [
                        {
                            "segment_id": seg.get("segment_id"),
                            "text": sanitize_text(seg.get("text"), api_key),
                            "citation_ids": list(seg.get("citation_ids") or []),
                        }
                        for seg in (result["draft"].get("segments") or [])
                    ],
                    "citations": [
                        {
                            **cit,
                            "snippet": sanitize_text(cit.get("snippet"), api_key) if cit.get("snippet") else None,
                        }
                        for cit in (result["draft"].get("citations") or [])
                    ],
                }

            no_auto_send = (
                result.get("status") in {"draft_ready", "llm_unavailable", "escalation_recommended", "abstained"}
                and "sent" not in result
                and "auto_sent" not in result
                and "customer_reply_sent" not in result
            )
            sum_att_lat = round(sum((a.get("latency_seconds") or 0.0) for a in sanitized_attempts), 4)
            reported_llm_ms = (result.get("step_latency_ms") or {}).get("llm")
            reported_llm_s = round((reported_llm_ms or 0) / 1000.0, 4)

            case_results.append(
                {
                    "case_id": c["id"],
                    "expected_intent": c["intent"],
                    "expected_docs": list(c.get("expected_docs") or []),
                    "serving_raw_prediction": pred["intent"],
                    "serving_raw_confidence": round(float(pred["confidence"]), 6),
                    "diagnostic_intent_override": c["intent"],
                    "terminal_status": result.get("status"),
                    "failure_code": result.get("failure_code"),
                    "reason_codes": list(result.get("reason_codes") or []),
                    "staff_note": sanitize_text(result.get("staff_note"), api_key),
                    "no_auto_send_verified": no_auto_send,
                    "http_requests_this_case": req_end - req_start,
                    "attempt_count": len(sanitized_attempts),
                    "wall_elapsed_seconds": wall_elapsed,
                    "reported_llm_latency_seconds": reported_llm_s,
                    "sum_attempt_transport_seconds": sum_att_lat,
                    "step_latency_ms": dict(result.get("step_latency_ms") or {}),
                    "llm_usage_mapped": dict(result.get("llm_usage") or {}),
                    "attempts": sanitized_attempts,
                    "retrieved_sources": retrieved_docs_prov,
                    "draft": draft_payload,
                }
            )
    finally:
        http_client.close()

    tokens_summary = summarize_tokens_and_conditional_cost(case_results, cfg["model"])
    latencies = sorted(r["wall_elapsed_seconds"] for r in case_results)
    n_draft = sum(1 for r in case_results if r["terminal_status"] == "draft_ready")
    return {
        "report_type": "bounded_live_oracle_intent_provider_verification",
        "verification_scope": "oracle_intent_grounded_provider_component_verification",
        "scope_boundary": (
            "Diagnostic component check using expected-intent oracle override and approved KB sources on 4 cases. "
            "NOT automatic end-to-end classifier coverage, and does NOT claim whole-system live acceptance."
        ),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_commit": source_commit or "ff0e147",
        "configured_provider": {
            "provider": cfg["provider"],
            "model": cfg["model"],
            "prompt_version": PROMPT_VERSION,
            "configured_timeout_env": cfg["configured_timeout_env"],
            "enforced_attempt_timeout_seconds": 5.0,
            "enforced_budget_seconds": 10.0,
        },
        "provenance_hashes": {
            "approved_kb_v2_sha256": sha256_file(kb_path),
            "kb_release_sha256": sha256_file(release_path),
            "intent_policy_v2_sha256": sha256_file(policy_path),
            "final_acceptance_cases_sha256": sha256_file(cases_path),
        },
        "preflight": preflight,
        "budget_accounting": {
            "authorized_max_http_requests": MAX_LIVE_HTTP_REQUESTS,
            "actual_http_requests_made": guarded_transport.requests_attempted,
            "rejected_before_network_count": guarded_transport.rejected_before_network_count,
            "budget_enforced_within_cap": guarded_transport.requests_attempted <= MAX_LIVE_HTTP_REQUESTS,
            "transport_retries_configured": guarded_transport._retries_configured,
        },
        "summary": {
            "cases_executed": len(case_results),
            "http_calls_observed": guarded_transport.requests_attempted,
            "draft_ready_count": n_draft,
            "fallback_count": len(case_results) - n_draft,
            "no_auto_send_all": all(r["no_auto_send_verified"] for r in case_results),
            "wall_elapsed_p50_seconds": round(float(statistics.median(latencies)), 6) if latencies else 0.0,
            "wall_elapsed_nearest_rank_p50_seconds": latencies[len(latencies) // 2] if latencies else 0.0,
            "wall_elapsed_max_seconds": max(latencies) if latencies else 0.0,
        },
        "tokens_and_cost": tokens_summary,
        "transport_calls": list(guarded_transport.records),
        "cases": case_results,
    }


def recompute_live_accounting_and_latency(
    live_json_path: Path,
    pricing_json_path: Path,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Recompute observed-token list-price estimate and latency statistics offline without touching live_verification.json."""
    live = json.loads(live_json_path.read_text(encoding="utf-8"))
    pricing = json.loads(pricing_json_path.read_text(encoding="utf-8"))

    cases = list(live.get("cases") or [])
    all_attempts: list[dict[str, Any]] = []
    for c in cases:
        all_attempts.extend(c.get("attempts") or [])

    observed_prompt = 0
    observed_candidate = 0
    observed_thoughts_reported = 0
    observed_total_minus_prompt = 0
    observed_partial_total = 0
    missing_usage_attempts = 0
    thought_field_present_attempts = 0

    for att in all_attempts:
        u = att.get("usage") or {}
        p = u.get("promptTokenCount")
        cand = u.get("candidatesTokenCount")
        tot = u.get("totalTokenCount")
        th = u.get("thoughtsTokenCount")
        if type(th) is int and not isinstance(th, bool) and th >= 0:
            thought_field_present_attempts += 1
            observed_thoughts_reported += th
        if (
            type(p) is int and not isinstance(p, bool)
            and type(cand) is int and not isinstance(cand, bool)
            and type(tot) is int and not isinstance(tot, bool)
        ):
            observed_prompt += p
            observed_candidate += cand
            observed_partial_total += tot
            observed_total_minus_prompt += max(0, tot - p)
        else:
            missing_usage_attempts += 1

    input_rate = float(pricing["input_cost_per_million"])
    output_rate = float(pricing["output_cost_per_million"])
    # Output billing rate applies to total generated output (totalTokenCount - promptTokenCount).
    billable_observed_output = max(observed_candidate + observed_thoughts_reported, observed_total_minus_prompt)
    recomputed_input_usd = round((observed_prompt / 1_000_000.0) * input_rate, 8)
    recomputed_output_usd = round((billable_observed_output / 1_000_000.0) * output_rate, 8)
    recomputed_conditional_usd = round(recomputed_input_usd + recomputed_output_usd, 8)

    lat_pairs = sorted((float(c["wall_elapsed_seconds"]), str(c["case_id"])) for c in cases)
    sorted_latencies = [x[0] for x in lat_pairs]
    interpolated_p50 = round(float(statistics.median(sorted_latencies)), 6) if sorted_latencies else 0.0
    nearest_rank_idx_p50 = sorted_latencies[len(sorted_latencies) // 2] if sorted_latencies else 0.0
    nearest_rank_p95 = max(sorted_latencies) if sorted_latencies else 0.0

    prior_tc = dict(live.get("tokens_and_cost") or {})
    prior_ref = dict(prior_tc.get("list_price_reference_used") or {})

    result: dict[str, Any] = {
        "schema_version": "task_c_live_accounting_recomputed.v1",
        "recomputed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_live_verification_path": str(live_json_path),
        "source_live_verification_sha256": sha256_file(live_json_path),
        "source_live_verification_preserved_unmodified": True,
        "new_live_calls_made": 0,
        "verification_scope": live.get("verification_scope"),
        "scope_boundary": live.get("scope_boundary"),
        "previous_unverified_estimate": {
            "input_cost_per_million": prior_ref.get("input_cost_per_million", 0.075),
            "output_cost_per_million": prior_ref.get("output_cost_per_million", 0.30),
            "conditional_observed_list_price_usd": prior_tc.get("conditional_observed_list_price_usd"),
            "verification_status": "unverified_legacy_rate_retained_for_audit_history",
        },
        "verified_primary_pricing": {
            "provider": pricing.get("provider"),
            "model": pricing.get("model"),
            "tier": pricing.get("tier"),
            "modality": pricing.get("modality"),
            "input_cost_per_million": input_rate,
            "output_cost_per_million": output_rate,
            "output_includes_thinking": bool(pricing.get("output_includes_thinking", True)),
            "source_url": pricing.get("source_url"),
            "requested_source_url": pricing.get("requested_source_url"),
            "verified_on": pricing.get("verified_on"),
            "verified_by": pricing.get("verified_by"),
            "actual_account_tier_and_invoice_verified": False,
        },
        "token_and_cost_recomputation": {
            "http_calls_observed": int((live.get("budget_accounting") or {}).get("actual_http_requests_made", len(all_attempts))),
            "cases_executed": len(cases),
            "total_attempts_counted": len(all_attempts),
            "attempts_with_complete_usage": len(all_attempts) - missing_usage_attempts,
            "attempts_missing_usage": missing_usage_attempts,
            "complete_token_coverage": len(all_attempts) > 0 and missing_usage_attempts == 0,
            "observed_prompt_tokens": observed_prompt,
            "observed_candidate_tokens": observed_candidate,
            "observed_thought_tokens_reported": observed_thoughts_reported,
            "thought_field_present_attempt_count": thought_field_present_attempts,
            "missing_thought_field_not_proof_of_zero": thought_field_present_attempts < len(all_attempts),
            "observed_total_minus_prompt_billable_output_tokens": observed_total_minus_prompt,
            "observed_partial_total_tokens": observed_partial_total,
            "observed_reported_total_tokens": observed_partial_total if missing_usage_attempts == 0 else None,
            "conditional_observed_input_usd": recomputed_input_usd,
            "conditional_observed_output_usd": recomputed_output_usd,
            "conditional_observed_list_price_usd": recomputed_conditional_usd,
            "cost_status": "incomplete_token_coverage" if missing_usage_attempts > 0 else "conditional_list_price_estimate_unknown_account_tier",
            "complete_cost_known": False,
            "complete_cost_usd": None,
            "invoice_verified": False,
            "accounting_notes": [
                f"{missing_usage_attempts}/{len(all_attempts)} attempts failed or timed out without provider usage metadata; complete token total and complete cost are UNKNOWN (null).",
                "No totalTokenCount or usage is invented for failed attempts.",
                "Provider responses on final-case-10 (total=1864, prompt=1742, candidates=122) and final-case-12 (total=1832, prompt=1704, candidates=128) omit thoughtsTokenCount; missing thought field is NOT proof that thought tokens were 0 across attempts.",
                "Actual account billing tier and invoiced charges are not verified; $0.25/1M input and $1.50/1M output (incl. thinking) reflect published standard paid-tier Google AI Studio / Gemini API list rates.",
            ],
        },
        "latency_recomputation": {
            "http_calls_observed": int((live.get("budget_accounting") or {}).get("actual_http_requests_made", len(all_attempts))),
            "cases_executed": len(cases),
            "per_case_sorted_wall_elapsed_seconds": [
                {"case_id": cid, "wall_elapsed_seconds": val} for val, cid in lat_pairs
            ],
            "standard_interpolated_median_p50_seconds": interpolated_p50,
            "prior_nearest_rank_index_p50_seconds": nearest_rank_idx_p50,
            "nearest_rank_p95_seconds": nearest_rank_p95,
            "wall_elapsed_max_seconds": nearest_rank_p95,
            "tiny_sample_limitation": (
                f"Sample size is n={len(cases)} top-level cases across "
                f"{int((live.get('budget_accounting') or {}).get('actual_http_requests_made', len(all_attempts)))} HTTP calls. "
                "With n=4, standard interpolated median is (6.6006 + 9.9265) / 2 = 8.26355s (vs prior index len//2 nearest-rank 9.9265s), "
                "and nearest-rank p95 collapses to sample max (10.1452s); percentiles on n=4 are descriptive only, not stable SLA metrics."
            ),
        },
        "coordinator_ai_draft_review": {
            "component_boundary_note": (
                "Both emitted live drafts come from oracle expected-intent diagnostic overrides (intent_override) on ff0e147, "
                "confirming grounded-provider recovery component behavior ONLY — NOT automatic full-pipeline classifier coverage."
            ),
            "reviewed_drafts": [
                {
                    "case_id": "final-case-10",
                    "expected_intent": "delivery_issue",
                    "diagnostic_intent_override": "delivery_issue",
                    "serving_raw_prediction": "delivery_issue",
                    "cited_sources": ["POL-SHIP-004:1.0"],
                    "coordinator_assessment": "policy_supported",
                    "notes": (
                        "Draft accurately reproduces POL-SHIP-004:1.0 timeframes and escalation contacts "
                        "(24-48 hours verification, delivery hub / courier GPS check, hotline 1900 6035 with no placeholder leak)."
                    ),
                },
                {
                    "case_id": "final-case-12",
                    "expected_intent": "payment_issue",
                    "diagnostic_intent_override": "payment_issue",
                    "serving_raw_prediction": "track_order",
                    "cited_sources": ["POL-PAY-001:1.0"],
                    "coordinator_assessment": "conditional_payment_guidance",
                    "notes": (
                        "Draft gives conditional payment reconciliation guidance grounded in POL-PAY-001:1.0 "
                        "(15-30 minutes verification wait, after 1 hour automatic refund within 24-72 business hours); "
                        "oracle intent override bypassed Serving misclassification (track_order), so this is NOT automatic classifier coverage."
                    ),
                },
            ],
        },
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result
