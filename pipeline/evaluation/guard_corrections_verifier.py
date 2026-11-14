"""Additive zero-live-call verification helpers for plan `c4520c1` guard & fault corrections.

Preserves historical `artifacts/evaluation/fault_boundaries_20261113/*` files untouched and
verifies:
1. Immutable sha256 digests of the baseline `8f7d542` fault-boundary evidence.
2. Real `GeminiDraftClient` valid-output vs invalid-injected-output behavior (0 live traffic).
3. Cross-customer `unc-track_order-05` intake 404 privacy preservation vs frozen conflict.
4. `final_acceptance` `product_12_answerable` ownership parity (`demo-customer` vs `cust_1`).
5. Worker B guard priority/clarify/negation/post-generation regressions & Worker A typed
   fault propagation across `RetrievalAdapter`, `ai_service`, `SuggestionWorker`, and `PipelineRunner`.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from fastapi.testclient import TestClient

from apps.core_backend.commerce.adapter import CommerceAdapter
from apps.core_backend.intent.client import IntentClient
from apps.core_backend.intent.routing import load_policy_v2
from apps.core_backend.intent.schemas import RoutingContext
from apps.core_backend.llm.gemini import GeminiDraftClient, LLMError
from apps.core_backend.orchestration.pipeline_runner import PipelineRunner
from apps.core_backend.orchestration.store import PersistentStore
from apps.core_backend.retrieval.adapter import RetrievalAdapter
from pipeline.evaluation.fault_boundary_runner import (
    REPO_ROOT,
    _resolve_model_dir,
)
from pipeline.evaluation.live_provider_verification import ALLOWED_GEMINI_HOST
from scripts.collect_final_acceptance_evidence import compute_sha256

HISTORIC_FAULT_BOUNDARY_SHA256: Dict[str, str] = {
    "fault_boundary_report.json": "348c4a1861450fcab290e3dd9517b46bac808f0cd9436973c4558f81fb1f48ae",
    "FAULT_BOUNDARY_REPORT.md": "8cd003fb59b41a32a4c0dc312b1ffbd207b9472200677fb5b7ea7bbff2bd266f",
}


def verify_historic_fault_evidence_unchanged(repo_root: Path = REPO_ROOT) -> Dict[str, Any]:
    """Assert prior `8f7d542` fault-boundary artifacts match their committed sha256 digests."""
    base = repo_root / "artifacts" / "evaluation" / "fault_boundaries_20261113"
    checks: Dict[str, Any] = {}
    all_match = True
    for filename, expected_sha in HISTORIC_FAULT_BOUNDARY_SHA256.items():
        path = base / filename
        actual_sha = compute_sha256(path) if path.exists() else None
        matched = actual_sha == expected_sha
        all_match = all_match and matched
        checks[filename] = {
            "exists": path.exists(),
            "expected_sha256": expected_sha,
            "actual_sha256": actual_sha,
            "matched": matched,
        }
    return {"all_matched": all_match, "files": checks}


def classify_corrected_fault_contract(record: Dict[str, Any]) -> Dict[str, Any]:
    """Attach explicit privacy-vs-frozen conflict metadata without mutating historical records."""
    exp = record.get("expected") or {}
    obs = record.get("observed") or {}
    details = record.get("details") or {}
    checks = record.get("checks") or {}
    case_id = record.get("case_id")
    fault = str(record.get("fault") or "")
    scenario = record.get("scenario")

    expected_actions = list(exp.get("actions") or [])
    expected_reason_any = list(exp.get("reason_any") or [])
    must_escalate = bool(exp.get("must_escalate", False))
    must_not_draft = bool(exp.get("must_not_draft", False))

    mapped_action = obs.get("mapped_action")
    reason_codes = list(obs.get("reason_codes") or [])
    http_status = obs.get("http_status")

    zero_tickets_created = (
        obs.get("tickets_created_delta") == 0
        or details.get("tickets_created_delta") == 0
        or obs.get("ticket_count_after_submit") == 0
        or details.get("ticket_count_after_submit") == 0
    )
    is_privacy_intake_404 = (
        case_id == "unc-track_order-05"
        and scenario == "backend_pg_explicit_unauthorized_order"
        and http_status == 404
        and zero_tickets_created
    )
    reason_any_matched = (
        any(r in reason_codes for r in expected_reason_any)
        if expected_reason_any
        else True
    )
    action_in_expected = (mapped_action in expected_actions) if mapped_action else False
    strict_must_escalate_matched = (not must_escalate) or (mapped_action == "escalate")

    note = None
    if is_privacy_intake_404:
        note = (
            "Cross-customer order_id intake intentionally returns HTTP 404 with 0 tickets created "
            "(privacy requirement); incompatible with frozen must_escalate=True / reason_any="
            f"{expected_reason_any}."
        )
    elif must_escalate and "manual_fallback" in expected_actions and mapped_action == "manual_fallback":
        note = (
            "Frozen fixture mixes contradictory must_escalate=True with expected.actions containing "
            "'manual_fallback'; safe fallback honored without drafting."
        )

    no_draft_base = bool(checks.get("no_draft_ok", obs.get("no_draft_preserved")))
    if must_not_draft and not fault.startswith("llm_"):
        no_draft_preserved = no_draft_base and (obs.get("llm_calls") == 0)
    else:
        no_draft_preserved = no_draft_base

    allowed_actions = (
        obs.get("allowed_actions")
        if obs.get("allowed_actions") is not None
        else details.get("allowed_actions")
    )

    return {
        "case_id": case_id,
        "fault": record.get("fault"),
        "surface": record.get("surface"),
        "scenario": scenario,
        "verdict": record.get("verdict"),
        "privacy_intake_404_preserved": is_privacy_intake_404,
        "safe_fallback_or_expected_action_matched": action_in_expected,
        "strict_must_escalate_matched": strict_must_escalate_matched,
        "strict_reason_any_matched": reason_any_matched,
        "no_draft_preserved": no_draft_preserved,
        "allowed_actions": allowed_actions,
        "is_authority_required": obs.get("is_authority_required"),
        "boundary_note": note,
    }


def make_mock_gemini_client(payload_mode: str = "valid_grounded") -> tuple[GeminiDraftClient, List[str]]:
    """Build a zero-network `GeminiDraftClient` backed by `httpx.MockTransport`."""
    requested_urls: List[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host != ALLOWED_GEMINI_HOST:
            raise AssertionError(f"Unexpected host in mock Gemini transport: {request.url.host}")
        requested_urls.append(str(request.url))
        if payload_mode == "valid_grounded":
            inner = {
                "answerable": True,
                "answer": "You may return eligible Tiki Trading items within 30 days via free Tiki courier pickup [S1].",
                "citations": ["S1"],
                "is_clarification": False,
            }
        elif payload_mode == "valid_clarification":
            inner = {
                "answerable": True,
                "answer": "Please confirm your item condition and packaging status; Tiki Trading returns apply within 30 days [S1].",
                "citations": ["S1"],
                "is_clarification": True,
            }
        elif payload_mode == "invalid_unknown_citation":
            inner = {
                "answerable": True,
                "answer": "Standard return policy applies here [S99].",
                "citations": ["S99"],
                "is_clarification": False,
            }
        elif payload_mode == "invalid_uncited":
            inner = {
                "answerable": True,
                "answer": "You can return products within 30 days with free pickup.",
                "citations": [],
                "is_clarification": False,
            }
        elif payload_mode == "unanswerable_flag":
            inner = {
                "answerable": False,
                "answer": "",
                "citations": [],
                "is_clarification": False,
            }
        else:
            raise ValueError(f"Unknown payload_mode: {payload_mode}")

        body = {
            "modelVersion": "gemini-2.5-flash",
            "usageMetadata": {
                "promptTokenCount": 42,
                "candidatesTokenCount": 18,
                "totalTokenCount": 60,
            },
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {"parts": [{"text": json.dumps(inner)}]},
                }
            ],
        }
        return httpx.Response(status_code=200, json=body)

    http_client = httpx.Client(transport=httpx.MockTransport(handler), trust_env=False)
    client = GeminiDraftClient(
        api_key="offline-mock-key",
        model="gemini-2.5-flash",
        http_client=http_client,
    )
    return client, requested_urls


class UnraisedInvalidLLMClient:
    """Offline injected LLM that returns invalid outputs directly without raising `LLMError`."""

    def __init__(self, mode: str) -> None:
        self.configured = True
        self.mode = mode
        self.calls: List[Dict[str, Any]] = []

    def generate(
        self,
        question: str,
        intent: str,
        evidence: List[Dict[str, Any]],
        business_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.calls.append({"question": question, "intent": intent, "evidence_count": len(evidence)})
        if self.mode == "unknown_citation":
            body = "Refunds follow policy terms [S99]."
            sources = [
                {
                    "source_id": "S1",
                    "id": "S1",
                    "source_type": "policy",
                    "document_id": evidence[0].get("document_id", "POL-RET-001"),
                    "version": str(evidence[0].get("version", "2.0")),
                    "excerpt": evidence[0].get("excerpt", ""),
                }
            ] if evidence else []
        elif self.mode == "uncited_long_claim":
            body = "You will receive a $50 refund within 7 business days automatically to your original payment method."
            sources = [
                {
                    "source_id": "S1",
                    "id": "S1",
                    "source_type": "policy",
                    "document_id": evidence[0].get("document_id", "POL-RET-001"),
                    "version": str(evidence[0].get("version", "2.0")),
                    "excerpt": evidence[0].get("excerpt", ""),
                }
            ] if evidence else []
        elif self.mode == "placeholder_leak":
            body = "Hello [NAME], refund details for [ORDER_ID] follow policy [S1]."
            sources = [
                {
                    "source_id": "S1",
                    "id": "S1",
                    "source_type": "policy",
                    "document_id": evidence[0].get("document_id", "POL-RET-001"),
                    "version": str(evidence[0].get("version", "2.0")),
                    "excerpt": evidence[0].get("excerpt", ""),
                }
            ] if evidence else []
        else:
            raise ValueError(f"Unsupported UnraisedInvalidLLMClient mode: {self.mode}")

        return {
            "body": body,
            "citations": [{"source_id": "S1", "source_type": "policy", "document_id": "POL-RET-001", "version": "2.0"}],
            "input_snapshot": {"sources": sources},
            "is_clarification": False,
            "provider": "offline_injected_spy",
            "model": "none",
            "latency_seconds": 0.001,
            "usage": {"promptTokenCount": 1, "candidatesTokenCount": 1},
        }


DEFAULT_B_REGRESSION_PROBES: Tuple[Tuple[str, str, str], ...] = (
    ("human_fraud_priority", "Let me talk to a human agent about this fraud lawsuit!", "must_escalate_manager"),
    ("human_fraud_return", "I want to talk to a human agent about a fraud exception on my refund!", "must_escalate_manager"),
    ("clarify_low_conf_fraud", "Where is my order? Actually this is fraud and I want a human agent!", "must_escalate"),
    ("clarify_missing_oid_tax", "How do I file my income tax return for this order?", "must_not_draft"),
    (
        "overlapping_scope_conflict",
        "What are the customs import duties and unratified 2022 rules for international shipping?",
        "must_escalate_over_abstain",
    ),
    ("negated_human", "I do not want to talk to a human agent, just tell me the return window.", "should_not_false_escalate_human"),
    ("negated_dispute", "What is the refund timeline if there is no payment dispute on my order?", "should_not_false_escalate_dispute"),
    ("negated_exception", "Do normal Tiki Trading items qualify without needing a manager exception?", "should_not_false_escalate_exception"),
    ("draft_verb_policy", "Can you draft a reply explaining the standard 30-day return policy?", "should_draft_supported"),
    ("expired_product_policy", "My skincare product arrived expired; what is your return policy?", "should_draft_supported"),
    ("purchase_year_current_policy", "I bought this item in 2025, what is the current 2026 return policy?", "should_draft_supported"),
    ("courier_pickup_ordinary", "Can I use free Tiki courier pickup to return a 2024 VND item?", "should_draft_supported"),
    ("privacy_policy_ordinary", "What is your return policy regarding customer privacy rules?", "should_draft_supported"),
)


def run_b_guard_and_ownership_probes(
    *,
    worktree_root: Path = REPO_ROOT,
    root_repo: Path = REPO_ROOT,
) -> Dict[str, Any]:
    """Run offline full HTTP/ASGI `PipelineRunner` & `Engine` probes on guard & ownership behavior."""
    import apps.ml_inference.app as ml_app
    from apps.ai_service.engine import Engine

    model_dir = _resolve_model_dir(worktree_root, root_repo)
    ml_app.container.load(model_dir=model_dir)
    tc = TestClient(ml_app.app)

    def bridge(req: httpx.Request) -> httpx.Response:
        r = tc.post(req.url.path, content=req.content, headers=dict(req.headers))
        return httpx.Response(status_code=r.status_code, content=r.content, headers=dict(r.headers))

    intent_client = IntentClient(
        base_url="http://ml-service",
        expected_model_version=ml_app.container.model_version,
        http_client=httpx.Client(transport=httpx.MockTransport(bridge), trust_env=False),
    )
    policy = load_policy_v2(str(worktree_root / "apps" / "core_backend" / "config" / "policies" / "intent_policy.v2.json"))
    release = json.loads((worktree_root / "apps" / "ai_service" / "kb-release.json").read_text(encoding="utf-8"))
    allowed_versions = {(d["document_id"], str(d["version"])) for d in release["documents"]}
    commerce = CommerceAdapter(data_path=str(worktree_root / "data" / "knowledge" / "mock_orders.json"))
    retrieval = RetrievalAdapter(
        kb_path=str(worktree_root / "data" / "knowledge" / "approved_kb.v2.json"),
        allowed_document_versions=allowed_versions,
    )

    fa_path = worktree_root / "data" / "benchmarks" / "final_acceptance" / "cases.jsonl"
    fa_rows = [json.loads(l) for l in fa_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    fa_ans = [c for c in fa_rows if c.get("slice") == "product_12_answerable"]

    probe_results: List[Dict[str, Any]] = []
    ownership_results: Dict[str, Any] = {}
    gemini_boundary_results: Dict[str, Any] = {}

    try:
        with tempfile.TemporaryDirectory() as td:
            # 1. Regression probes on PipelineRunner with valid GeminiDraftClient mock
            gemini_valid, gemini_urls = make_mock_gemini_client("valid_grounded")
            try:
                runner = PipelineRunner(
                    intent_client=intent_client,
                    policy=policy,
                    commerce_adapter=commerce,
                    retrieval_adapter=retrieval,
                    store=PersistentStore(str(Path(td) / "probes.sqlite3")),
                    llm_client=gemini_valid,
                    clock=lambda: datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                )
                for tag, text_q, expectation in DEFAULT_B_REGRESSION_PROBES:
                    ctx = RoutingContext(
                        ticket_customer_id="demo-customer",
                        verified_scope="ticket:read order:read",
                        as_of="2026-06-15T10:00:00+00:00",
                    )
                    res = runner.run(text_q, ctx, run_id=f"probe-{tag}")
                    probe_results.append(
                        {
                            "tag": tag,
                            "expectation": expectation,
                            "query": text_q,
                            "initial_routing_action": res.get("initial_routing_action"),
                            "action": res.get("action"),
                            "predicted_intent": res.get("predicted_intent"),
                            "final_intent": res.get("final_intent"),
                            "target_queue": res.get("target_queue"),
                            "requested_team": res.get("requested_team"),
                            "reason_codes": res.get("reason_codes"),
                            "llm_called": res.get("llm_called"),
                            "draft_generated": bool(res.get("draft_body")),
                            "confidence": res.get("confidence"),
                            "margin": res.get("margin"),
                        }
                    )

                # 2. GeminiDraftClient legitimate output check & score immutability
                clean_res = runner.run(
                    "What is the return window for Tiki Trading products?",
                    RoutingContext(
                        ticket_customer_id="demo-customer",
                        verified_scope="ticket:read order:read",
                        as_of="2026-06-15T10:00:00+00:00",
                    ),
                    run_id="gemini-valid-pr",
                )
                ai_policy = json.loads(
                    (worktree_root / "apps" / "core_backend" / "config" / "policies" / "intent_policy.v2.json").read_text(
                        encoding="utf-8"
                    )
                )
                eng_valid = Engine(
                    ml_app.container,
                    retrieval,
                    gemini_valid,
                    {"release_id": "offline-check"},
                    ai_policy,
                )
                eng_valid_res = eng_valid.draft(
                    {
                        "message": "What is the return window for Tiki Trading products?",
                        "order_context": {},
                        "as_of": "2026-06-15T10:00:00Z",
                    }
                )
                gemini_boundary_results["valid_gemini_mock"] = {
                    "pipeline_action": clean_res.get("action"),
                    "pipeline_has_draft": bool(clean_res.get("draft_body")),
                    "pipeline_confidence": clean_res.get("confidence"),
                    "pipeline_margin": clean_res.get("margin"),
                    "engine_status": eng_valid_res.get("status"),
                    "engine_has_draft": bool(eng_valid_res.get("draft")),
                    "mock_http_calls": len(gemini_urls),
                }
            finally:
                gemini_valid.close()

            # 3. Default GeminiDraftClient rejects invalid JSON citations internally
            gemini_bad_cit, _ = make_mock_gemini_client("invalid_unknown_citation")
            try:
                caught_code = None
                try:
                    gemini_bad_cit.generate(
                        "What is the return window?",
                        "return_policy",
                        [{"source_type": "policy", "document_id": "POL-RET-001", "version": "2.0", "excerpt": "30 days."}],
                    )
                except LLMError as exc:
                    caught_code = exc.code
                gemini_boundary_results["default_client_invalid_citation_error"] = caught_code
            finally:
                gemini_bad_cit.close()

            # 4. Injected unraised invalid outputs across Engine and PipelineRunner
            injected_checks: Dict[str, Any] = {}
            ai_policy = json.loads(
                (worktree_root / "apps" / "core_backend" / "config" / "policies" / "intent_policy.v2.json").read_text(
                    encoding="utf-8"
                )
            )
            for inj_mode in ("unknown_citation", "uncited_long_claim", "placeholder_leak"):
                spy_pr = UnraisedInvalidLLMClient(inj_mode)
                runner_inj = PipelineRunner(
                    intent_client=intent_client,
                    policy=policy,
                    commerce_adapter=commerce,
                    retrieval_adapter=retrieval,
                    store=PersistentStore(str(Path(td) / f"inj-{inj_mode}.sqlite3")),
                    llm_client=spy_pr,
                    clock=lambda: datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                )
                pr_out = runner_inj.run(
                    "What is the return window for Tiki Trading items?",
                    RoutingContext(
                        ticket_customer_id="demo-customer",
                        verified_scope="ticket:read order:read",
                        as_of="2026-06-15T10:00:00+00:00",
                    ),
                    run_id=f"inj-{inj_mode}",
                )
                spy_eng = UnraisedInvalidLLMClient(inj_mode)
                eng_inj = Engine(ml_app.container, retrieval, spy_eng, {"release_id": "offline-check"}, ai_policy)
                eng_out = eng_inj.draft(
                    {
                        "message": "What is the return window for Tiki Trading items?",
                        "order_context": {},
                        "as_of": "2026-06-15T10:00:00Z",
                    }
                )
                injected_checks[inj_mode] = {
                    "pipeline_action": pr_out.get("action"),
                    "pipeline_reason_codes": pr_out.get("reason_codes"),
                    "pipeline_draft_body_present": bool(pr_out.get("draft_body")),
                    "engine_status": eng_out.get("status"),
                    "engine_reason_codes": eng_out.get("reason_codes"),
                    "engine_draft_present": bool(eng_out.get("draft")),
                }
            gemini_boundary_results["unraised_injected_llm_outputs"] = injected_checks

            # 5. Comparable ownership check on final_acceptance product_12_answerable
            for cid in ("cust_1", "demo-customer"):
                g_cli, _ = make_mock_gemini_client("valid_grounded")
                try:
                    r_own = PipelineRunner(
                        intent_client=intent_client,
                        policy=policy,
                        commerce_adapter=commerce,
                        retrieval_adapter=retrieval,
                        store=PersistentStore(str(Path(td) / f"own-{cid}.sqlite3")),
                        llm_client=g_cli,
                        clock=lambda: datetime(2026, 6, 15, 10, 0, tzinfo=timezone.utc),
                    )
                    raw_draft = 0
                    correct_draft = 0
                    unauth_count = 0
                    rows_out = []
                    for c in fa_ans:
                        slots = {"order_id": c["order_id"]} if c.get("order_id") else {}
                        ctx = RoutingContext(
                            ticket_customer_id=cid,
                            verified_scope="ticket:read order:read",
                            is_personal_lookup=bool(c.get("order_id")),
                            extracted_slots=slots,
                            as_of=c.get("as_of"),
                        )
                        out = r_own.run(c["query"], ctx, run_id=f"own-{cid}-{c['id']}")
                        if out.get("action") == "retrieve_draft" and out.get("draft_body"):
                            raw_draft += 1
                            if out.get("final_intent") == c.get("intent"):
                                correct_draft += 1
                        if any("commerce_unauthorized" in rc for rc in (out.get("reason_codes") or [])):
                            unauth_count += 1
                        rows_out.append(
                            {
                                "id": c["id"],
                                "expected_intent": c.get("intent"),
                                "predicted_intent": out.get("predicted_intent"),
                                "initial_action": out.get("initial_routing_action"),
                                "final_action": out.get("action"),
                                "reason_codes": out.get("reason_codes"),
                            }
                        )
                    ownership_results[cid] = {
                        "total": len(fa_ans),
                        "raw_draft": raw_draft,
                        "correct_intent_draft": correct_draft,
                        "commerce_unauthorized_count": unauth_count,
                        "cases": rows_out,
                    }
                finally:
                    g_cli.close()
    finally:
        intent_client.close()

    return {
        "worktree_root": str(worktree_root),
        "b_regression_probes": probe_results,
        "gemini_boundary_checks": gemini_boundary_results,
        "final_acceptance_answerable_ownership": ownership_results,
    }
