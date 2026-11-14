"""ML suite: intent classifier + the real routing gates on frozen datasets."""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from apps.core_backend.intent.routing import INTENT_TO_QUEUE_MAP, SUPPORTED_12_INTENTS, decide_route, load_policy_v2
from apps.core_backend.intent.channels import names_return_channel
from apps.core_backend.intent.schemas import ClausePrediction, IntentPrediction, RoutingContext

from . import metrics as M
from .backends import IntentModel, load_model_dirs, verify_model
from .build_intent_set import verify_manifest as verify_intent_set
from .datasets import REPO_ROOT, load_jsonl

ML_FAULTS = {"ml_timeout", "ml_error"}
SUPPORTED = set(SUPPORTED_12_INTENTS)


def _route(policy, pred: dict | None, context: dict, model_version: str, fault: str | None = None, text: str = ""):
    if fault in ML_FAULTS or pred is None:
        p = IntentPrediction(intent="unknown", confidence=0.0, margin=0.0, model_version=model_version, error=fault or "ml_error")
    else:
        clauses = [ClausePrediction(**c) for c in pred["clauses"]] if pred.get("clauses") else None
        p = IntentPrediction(intent=pred["intent"], confidence=pred["confidence"], margin=pred["margin"],
                             model_version=model_version, clauses=clauses,
                             scope_probability=pred.get("scope_probability"))
    # Same flag as PipelineRunner sets from the message (docs/design/return-channel-guard.md).
    context = {**context, "return_channel_named": bool(policy.return_channel_guard and names_return_channel(text))}
    return decide_route(p, RoutingContext(**context), policy)


def _predict(model: IntentModel, policy, text: str) -> dict:
    """Whole-message prediction plus clauses when the policy enables multi-request detection, as in serving."""
    pred = model.predict(text)
    multi = policy.multi_request
    if multi is not None and multi.enabled:
        pred["clauses"] = model.predict_clauses(text, multi.min_words, multi.max_clauses, multi.request_clauses_only)
    return pred


def _threshold(policy, intent: str) -> float:
    return policy.confidence_thresholds.get(intent, policy.default_confidence_threshold)


def run(config: dict, backend: str = "auto", log=print) -> dict[str, Any]:
    cfg = config["ml"]
    # A comma-separated model_dir is a seed ensemble (docs/design/intent-model-v1.2.md): logits are averaged.
    dirs = [d.strip() for d in cfg["model_dir"].split(",") if d.strip()]
    checks = [verify_model(REPO_ROOT / d) for d in dirs]
    check = checks[0] if len(checks) == 1 else {
        **checks[0], "members": checks, "ok": all(c.get("ok") for c in checks),
        "checksum_match": all(c.get("checksum_match") for c in checks)}
    out: dict[str, Any] = {"model": check}
    if any("weights_sha256" not in c for c in checks):
        out["error"] = next((c.get("error") for c in checks if "weights_sha256" not in c), "model not found")
        return out
    model = IntentModel(load_model_dirs(cfg["model_dir"], REPO_ROOT, backend))
    out["backend"] = model.backend.name
    if getattr(model.backend, "fallback_reason", None):
        out["backend_fallback_reason"] = model.backend.fallback_reason
        log(f"[ml] torch backend unavailable, using numpy ({model.backend.fallback_reason})")
    policy = load_policy_v2(str(REPO_ROOT / cfg["policy"]))
    out["policy_version"] = policy.version
    mv = check.get("pinned_model_version") or "v1.0.0"
    # The gate set (ADR-0016) may differ from the LLM suite's data; it is used only when its manifest matches.
    root = REPO_ROOT / cfg.get("sets_dir", config["autoeval_dir"])
    bench_path = REPO_ROOT / cfg.get("benchmark", config["benchmark"])
    if "sets_dir" in cfg:
        frozen = verify_intent_set(root)
        out["frozen_set"] = {"dir": cfg["sets_dir"], **frozen}
        if not frozen["ok"]:
            out["error"] = f"frozen intent set does not match its manifest: {frozen}"
            return out

    # ---------------------------------------------------------------- benchmark (written queries)
    bench = load_jsonl(bench_path)
    log(f"[ml] benchmark: {len(bench)} cases ({model.backend.name} backend)")
    rows = []
    for c in bench:
        fault = c.get("fault")
        pred = None if fault in ML_FAULTS else _predict(model, policy, c["text"])
        d = _route(policy, pred, c["context"], mv, fault, c["text"])
        rows.append({"id": c["id"], "slice": c["primary_slice"], "text": c["text"], "gold": c.get("true_intent"),
                     "pred": pred and pred["intent"], "conf": pred and pred["confidence"], "margin": pred and pred["margin"],
                     "entropy": pred and pred["entropy"], "top_k": pred and pred["top_k"], "fault": fault,
                     "action": d.action, "reasons": d.reason_codes, "team": d.requested_team,
                     "exp_actions": c["expected"]["actions"], "exp_team": c["expected"].get("team"),
                     "must_escalate": c["expected"]["must_escalate"]})
    lab = [r for r in rows if r["gold"] and r["pred"]]
    gold, pred = [r["gold"] for r in lab], [r["pred"] for r in lab]
    correct = [g == p for g, p in zip(gold, pred)]
    ece, reliability = M.expected_calibration_error([r["conf"] for r in lab], correct)
    by_slice = {}
    for sl in sorted({r["slice"] for r in lab}):
        s = [r for r in lab if r["slice"] == sl]
        by_slice[sl] = {"n": len(s), "accuracy": M.accuracy([r["gold"] for r in s], [r["pred"] for r in s]),
                        "macro_f1": M.macro_f1([r["gold"] for r in s], [r["pred"] for r in s]),
                        "median_confidence": M.percentile([r["conf"] for r in s], 50)}

    # routing behaviour
    downstream = set(cfg.get("downstream_faults", []))
    must_not_draft = [r for r in rows if "retrieve_draft" not in r["exp_actions"] and r["slice"] != "unanswerable"
                      and (r["fault"] is None or r["fault"] in ML_FAULTS)]
    draftable = [r for r in rows if "retrieve_draft" in r["exp_actions"] and not r["must_escalate"] and r["fault"] is None]
    drafts = [r for r in rows if r["action"] == "retrieve_draft"]
    must_esc = [r for r in rows if r["must_escalate"]]
    esc = [r for r in rows if r["action"] == "escalate" and r["exp_team"]]
    routing = {
        "action_distribution": dict(Counter(r["action"] for r in rows)),
        "action_in_expected_rate": M.rate(sum(r["action"] in r["exp_actions"] for r in rows), len(rows)),
        "must_escalate": {"n": len(must_esc),
                          "escalate_or_fallback": sum(r["action"] in ("escalate", "manual_fallback") for r in must_esc),
                          "clarify": sum(r["action"] == "clarify" for r in must_esc),
                          "forwarded_to_draft": sum(r["action"] == "retrieve_draft" for r in must_esc),
                          "forwarded_to_draft_downstream_responsibility": sum(
                              r["action"] == "retrieve_draft" and (r["slice"] == "unanswerable" or (r["fault"] in downstream)) for r in must_esc)},
        "ml_unsafe_drafts": sum(r["action"] == "retrieve_draft" for r in must_not_draft),
        "ml_unsafe_draft_cases": [r["id"] for r in must_not_draft if r["action"] == "retrieve_draft"],
        "draftable_n": len(draftable),
        "draftable_reached_draft_rate": M.rate(sum(r["action"] == "retrieve_draft" for r in draftable), len(draftable)),
        "clarify_rate_on_draftable": M.rate(sum(r["action"] == "clarify" for r in draftable), len(draftable)),
        "wrong_intent_drafts": sum(1 for r in drafts if r["gold"] and r["pred"] != r["gold"]),
        "drafts_n": len(drafts),
        "escalation_team_accuracy": M.rate(sum(r["team"] == r["exp_team"] for r in esc), len(esc)),
        "reason_codes": dict(Counter(x for r in rows for x in r["reasons"]).most_common()),
        # Single-request labelled messages flagged as multiple requests (design: multi-request-detection).
        "multiple_requests_false_flags": sum("multiple_requests" in r["reasons"] for r in rows if r["gold"]),
    }
    out["benchmark"] = {
        "n_cases": len(rows), "n_labeled": len(lab),
        "accuracy": M.accuracy(gold, pred), "macro_f1": M.macro_f1(gold, pred),
        "team_accuracy": M.accuracy([INTENT_TO_QUEUE_MAP[g] for g in gold], [INTENT_TO_QUEUE_MAP[p] for p in pred]),
        "scope_accuracy": M.accuracy([g in SUPPORTED for g in gold], [p in SUPPORTED for p in pred]),
        "supported_intent_accuracy": by_slice.get("supported", {}).get("accuracy"),
        "by_slice": by_slice,
        "calibration": {"ece": ece, "reliability": reliability,
                        "confident_errors": sum(1 for r, ok in zip(lab, correct) if not ok and r["conf"] >= cfg["confident_error_threshold"]),
                        "selective_accuracy": M.selective_accuracy([r["conf"] for r in lab], correct)},
        "top_confusions": [[g, p, n] for (g, p), n in Counter((g, p) for g, p in zip(gold, pred) if g != p).most_common(10)],
        "per_class": M.per_class_f1(gold, pred),
        "routing": routing,
        "errors": [{k: r[k] for k in ("id", "slice", "text", "gold", "pred", "conf", "action")} for r in lab if r["gold"] != r["pred"]],
    }

    # ---------------------------------------------------------------- noise robustness (NFR-02)
    noise = load_jsonl(root / "ml_noise.jsonl")
    log(f"[ml] noise: {len(noise)} variants")
    by_kind = defaultdict(list)
    for n in noise:
        p = model.predict(n["text"])
        by_kind[n["kind"]].append((n["true_intent"], p["intent"], p["confidence"]))
    nres = {}
    for kind, v in by_kind.items():
        g, p = [x[0] for x in v], [x[1] for x in v]
        nres[kind] = {"n": len(v), "accuracy": M.accuracy(g, p), "macro_f1": M.macro_f1(g, p),
                      "median_confidence": M.percentile([x[2] for x in v], 50)}
    clean_f1 = nres.get("clean", {}).get("macro_f1")
    for kind in ("typo", "casual"):
        if kind in nres and clean_f1 is not None:
            nres[f"{kind}_f1_drop"] = clean_f1 - nres[kind]["macro_f1"]
    nres["max_f1_drop"] = max((nres.get(k) or 0.0) for k in ("typo_f1_drop", "casual_f1_drop"))
    out["noise"] = nres

    # ---------------------------------------------------------------- out-of-scope / vague / multi-intent (NFR-02)
    oos = load_jsonl(root / "ml_oos.jsonl")
    log(f"[ml] out-of-scope: {len(oos)} cases")
    orows = []
    for o in oos:
        p = _predict(model, policy, o["text"])
        d = _route(policy, p, o["context"], mv, text=o["text"])
        low = p["confidence"] < _threshold(policy, p["intent"])
        orows.append({"id": o["id"], "category": o["category"], "text": o["text"], "pred": p["intent"], "conf": p["confidence"],
                      "entropy": p["entropy"], "low_conf": low, "action": d.action,
                      "flagged": low or d.action != "retrieve_draft"})
    cats = {}
    for cat in sorted({r["category"] for r in orows}):
        s = [r for r in orows if r["category"] == cat]
        cats[cat] = {"n": len(s), "flagged_rate": M.rate(sum(r["flagged"] for r in s), len(s)),
                     "low_conf_rate": M.rate(sum(r["low_conf"] for r in s), len(s)),
                     "drafted": sum(r["action"] == "retrieve_draft" for r in s)}
    in_scope = [r for r in lab if r["slice"] in ("supported", "answerable")]
    out["oos"] = {
        "n": len(orows),
        "flagged_rate": M.rate(sum(r["flagged"] for r in orows), len(orows)),
        "low_conf_rate": M.rate(sum(r["low_conf"] for r in orows), len(orows)),
        "drafted": sum(r["action"] == "retrieve_draft" for r in orows),
        "by_category": cats,
        "auroc_entropy": M.auroc([r["entropy"] for r in in_scope], [r["entropy"] for r in orows]),
        "auroc_one_minus_conf": M.auroc([1 - r["conf"] for r in in_scope], [1 - r["conf"] for r in orows]),
        "confident_misses": [{k: r[k] for k in ("id", "text", "pred", "conf", "action")}
                             for r in orows if not r["low_conf"] and r["conf"] >= cfg["confident_error_threshold"]],
    }
    out["latency_ms"] = {"backend": model.backend.name, "n": len(model.latencies_ms),
                         "p50": M.percentile(model.latencies_ms, 50), "p95": M.percentile(model.latencies_ms, 95),
                         "note": "Per-sentence model compute only; numpy backend is not representative of the torch service."}
    return out
