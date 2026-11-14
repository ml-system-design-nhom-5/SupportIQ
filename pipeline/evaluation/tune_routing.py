"""Tune the routing configuration for an intent model on development data only (DATA-58).

Searches the multi-request gate (``min_clause_confidence``, ``min_words``; docs/design/multi-request-detection.md),
a uniform shift of the per-intent confidence thresholds (tau), and the default margin threshold (delta), using:

* ``data/intent/dev/v1/cases.synthetic-dev-only.psv``  - labelled single-request messages
* ``data/intent/dev/v1/oos.synthetic-dev-only.psv``    - out-of-domain messages
* ``data/intent/dev_multi/v1/cases.synthetic-dev-only.psv`` - multi-request messages and single-request hard negatives
* ``data/intent/dev_escalation/v1/cases.synthetic-dev-only.psv`` - product_issue and channel returns (counted as dev)

It never reads ``data/benchmarks/`` (DATA-25). Every message goes through the real ``decide_route``.

Selection: among settings that meet every constraint, the one with the most correct drafts on draftable dev
messages; ties go to the setting closest to the base policy. Without a feasible setting, the smallest total
constraint violation wins and the report says so.

    python -m pipeline.evaluation.tune_routing --model-dir artifacts/models/trained/distilbert-supportiq-v1.1.0 \
        --out artifacts/training/intent-v1.1.0/routing_tuning.json --write-policy
"""
from __future__ import annotations

import argparse
import itertools
import json
import sys
from pathlib import Path

from apps.core_backend.intent.channels import names_return_channel
from apps.core_backend.intent.routing import SUPPORTED_12_INTENTS, decide_route, load_policy_v2
from apps.core_backend.intent.schemas import ClausePrediction, IntentPrediction, MultiRequestPolicy, RoutingContext
from pipeline.evaluation.autoeval.backends import IntentModel, load_model_dirs
from pipeline.evaluation.autoeval import metrics as M
from pipeline.preparation.intent_extra import (load_dev_set, load_escalation_dev, load_independent_dev, load_multi_dev,
                                               load_oos_dev)

REPO_ROOT = Path(__file__).resolve().parents[2]
BASE_POLICY = REPO_ROOT / "apps/core_backend/config/policies/intent_policy.v2.json"
NEW_POLICY = REPO_ROOT / "apps/core_backend/config/policies/intent_policy.v3.json"

GRIDS = {
    # Policy v3 for v1.1.0 (docs/design/multi-request-detection.md).
    "v3": {
        "min_clause_confidence": [0.5, 0.6, 0.7, 0.8, 0.9],
        "min_words": [2, 3, 4],
        "tau_shift": [-0.10, -0.05, 0.0, 0.05, 0.10],
        "delta": [0.05, 0.10, 0.15, 0.20],
        "request_clauses_only": [False, True],
        "min_scope_probability": [None],
    },
    # Policy v4 for v1.2.0 (docs/design/intent-model-v1.2.md): adds gate 2f.
    "v4": {
        "min_clause_confidence": [0.5, 0.6, 0.7, 0.8, 0.9],
        "min_words": [3],
        "tau_shift": [-0.10, -0.05, 0.0, 0.05, 0.10],
        "delta": [0.05, 0.10, 0.15],
        "request_clauses_only": [True],
        "min_scope_probability": [None, 0.5, 0.6, 0.7, 0.8, 0.9],
    },
}
# Round 1 of v1.2 retunes without gate 2f, so each round's change is measured on its own.
GRIDS["v4-noscope"] = {**GRIDS["v4"], "min_scope_probability": [None]}
GRID = GRIDS["v3"]
BASE = {"min_words": 3, "tau_shift": 0.0, "delta": 0.10}
CONSTRAINTS = {  # metric: (op, bound)
    "multi_flag_rate": (">=", 0.90),
    "single_false_flag_rate": ("<=", 0.10),
    "dev_clarify_rate": ("<=", 0.15),
    "oos_flag_rate": (">=", 0.90),
}
MAX_CLAUSES = 4


def _context(text: str) -> RoutingContext:
    channel = names_return_channel(text)
    if "[ORDER_ID" in text:
        return RoutingContext(ticket_customer_id="dev", verified_scope="ticket:read order:read", is_personal_lookup=True,
                              extracted_slots={"order_id": "[ORDER_ID_1]"}, return_channel_named=channel)
    return RoutingContext(ticket_customer_id="dev", return_channel_named=channel)


def _policy(base, tau_shift: float, delta: float, min_conf: float, min_words: int, requests_only: bool = False,
            min_scope: float | None = None):
    # Thresholds of sensitive-action intents and their stricter per-intent margins are never lowered (guardrail).
    p = base.model_copy(deep=True)
    sensitive = set(base.sensitive_action_intents)
    p.confidence_thresholds = {
        k: round(min(0.95, max(0.30, v + tau_shift, v if k in sensitive else 0.0)), 2)
        for k, v in base.confidence_thresholds.items()
    }
    p.default_confidence_threshold = round(min(0.95, max(0.30, base.default_confidence_threshold + tau_shift)), 2)
    p.default_margin_threshold = delta
    p.margin_thresholds = {k: max(v, delta) for k, v in base.margin_thresholds.items()}
    p.multi_request = MultiRequestPolicy(min_clause_confidence=min_conf, min_words=min_words, max_clauses=MAX_CLAUSES,
                                         request_clauses_only=requests_only)
    p.return_channel_guard = True  # docs/design/return-channel-guard.md; not a tuned setting
    p.min_scope_probability = min_scope
    return p


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


def evaluate(items: list[dict], policy) -> dict:
    """``items``: dicts with ``group`` (dev|oos|multi|single), ``gold``, ``text``, ``pred``, ``clauses`` by min_words."""
    mw = (policy.multi_request.min_words, policy.multi_request.request_clauses_only)
    out = {"multi": [], "single": [], "dev": [], "oos": []}
    for it in items:
        p = it["pred"]
        clauses = it["clauses"][mw] if policy.multi_request.enabled else None
        pred = IntentPrediction(intent=p["intent"], confidence=p["confidence"], margin=p["margin"], model_version="dev",
                                clauses=[ClausePrediction(**c) for c in clauses] if clauses else None,
                                scope_probability=p.get("scope_probability"))
        d = decide_route(pred, _context(it["text"]), policy)
        low = p["confidence"] < policy.confidence_thresholds.get(p["intent"], policy.default_confidence_threshold)
        out[it["group"]].append({"gold": it["gold"], "pred": p["intent"], "conf": p["confidence"], "action": d.action,
                                 "reasons": d.reason_codes, "flagged": low or d.action != "retrieve_draft"})
    draftable = [r for r in out["dev"] if r["gold"] in SUPPORTED_12_INTENTS and r["gold"] != "human_agent"]
    must_escalate = [r for r in out["dev"] if r["gold"] not in SUPPORTED_12_INTENTS or r["gold"] == "human_agent"]
    return {
        "multi_flag_rate": _rate(sum(r["flagged"] for r in out["multi"]), len(out["multi"])),
        "multi_flagged_by_gate_rate": _rate(sum("multiple_requests" in r["reasons"] for r in out["multi"]), len(out["multi"])),
        "single_false_flag_rate": _rate(sum("multiple_requests" in r["reasons"] for r in out["single"]), len(out["single"])),
        "single_draft_rate": _rate(sum(r["action"] == "retrieve_draft" for r in out["single"]), len(out["single"])),
        "dev_clarify_rate": _rate(sum(r["action"] == "clarify" for r in draftable), len(draftable)),
        "dev_correct_draft_rate": _rate(sum(r["action"] == "retrieve_draft" and r["pred"] == r["gold"] for r in draftable), len(draftable)),
        "dev_wrong_intent_drafts": sum(r["action"] == "retrieve_draft" and r["pred"] != r["gold"] for r in out["dev"]),
        "dev_must_escalate_drafted": sum(r["action"] == "retrieve_draft" for r in must_escalate),
        "oos_flag_rate": _rate(sum(r["flagged"] for r in out["oos"]), len(out["oos"])),
        "dev_macro_f1": round(M.macro_f1([r["gold"] for r in out["dev"]], [r["pred"] for r in out["dev"]]), 4) if out["dev"] else None,
        "dev_confident_error_rate": _rate(sum(r["pred"] != r["gold"] and r["conf"] >= 0.8 for r in out["dev"]), len(out["dev"])),
        "n": {k: len(v) for k, v in out.items()} | {"draftable": len(draftable)},
    }


def violation(metrics: dict) -> float:
    total = 0.0
    for name, (op, bound) in CONSTRAINTS.items():
        v = metrics[name]
        total += max(0.0, bound - v) if op == ">=" else max(0.0, v - bound)
    return round(total, 4)


def select(results: list[dict]) -> dict:
    def distance(r):
        s = r["settings"]
        return (abs(s["tau_shift"] - BASE["tau_shift"]) + abs(s["delta"] - BASE["delta"])
                + 0.01 * abs(s["min_words"] - BASE["min_words"]) - 0.001 * s["min_clause_confidence"])
    # Must-escalate dev messages sent to drafting come first: no routing setting may trade them for more drafts.
    feasible = [r for r in results if r["violation"] == 0]
    pool = feasible or results
    key = (lambda r: (r["metrics"]["dev_must_escalate_drafted"], -r["metrics"]["dev_correct_draft_rate"],
                      r["metrics"]["dev_wrong_intent_drafts"], distance(r))) if feasible \
        else (lambda r: (r["violation"], r["metrics"]["dev_must_escalate_drafted"], -r["metrics"]["dev_correct_draft_rate"], distance(r)))
    best = min(pool, key=key)
    return {**best, "feasible": bool(feasible), "n_feasible": len(feasible)}


def load_items(model: IntentModel, grid: dict = GRID, independent: bool = False) -> list[dict]:
    """Dev messages with predictions. ``independent`` adds data/intent/dev_independent (source ``independent``)."""
    rows = [("own", "dev", r.intent, r.instruction) for r in load_dev_set().itertuples()]
    rows += [("own", "dev", r.intent, r.instruction) for r in load_escalation_dev().itertuples()]
    rows += [("own", "oos", None, r.instruction) for r in load_oos_dev().itertuples()]
    rows += [("own", r.kind, None, r.instruction) for r in load_multi_dev().itertuples()]
    if independent:
        group = {"labelled": "dev", "oos": "oos", "multi": "multi"}
        rows += [("independent", group[r["kind"]], r["true_intent"] if r["kind"] == "labelled" else None, r["text"])
                 for r in load_independent_dev()]
    items = []
    for source, group, gold, text in rows:
        items.append({"source": source, "group": group, "gold": gold, "text": text, "pred": model.predict(text),
                      "clauses": {(mw, ro): model.predict_clauses(text, mw, MAX_CLAUSES, ro)
                                  for mw in grid["min_words"] for ro in grid["request_clauses_only"]}})
    return items


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--backend", default="auto", choices=["auto", "torch", "numpy"])
    ap.add_argument("--out", required=True, help="JSON report path")
    ap.add_argument("--write-policy", action="store_true", help=f"write {NEW_POLICY.relative_to(REPO_ROOT).as_posix()}")
    ap.add_argument("--model-version", default="v1.1.0")
    ap.add_argument("--grid", default="v3", choices=sorted(GRIDS))
    ap.add_argument("--policy-version", default="v3.0.0")
    ap.add_argument("--policy-out", default=str(NEW_POLICY.relative_to(REPO_ROOT)))
    ap.add_argument("--independent", action="store_true", help="also use data/intent/dev_independent")
    args = ap.parse_args(argv)

    grid = GRIDS[args.grid]
    model = IntentModel(load_model_dirs(args.model_dir, REPO_ROOT, args.backend))
    base = load_policy_v2(str(BASE_POLICY))
    items = load_items(model, grid, args.independent)
    results = []
    for values in itertools.product(*grid.values()):
        st = dict(zip(grid, values))
        policy = _policy(base, st["tau_shift"], st["delta"], st["min_clause_confidence"], st["min_words"],
                         st["request_clauses_only"], st["min_scope_probability"])
        m = evaluate(items, policy)
        results.append({"settings": st, "metrics": m, "violation": violation(m)})
    best = select(results)
    s = best["settings"]
    chosen = _policy(base, s["tau_shift"], s["delta"], s["min_clause_confidence"], s["min_words"],
                     s["request_clauses_only"], s["min_scope_probability"])
    by_source = {src: evaluate([it for it in items if it["source"] == src], chosen)
                 for src in sorted({it["source"] for it in items})}
    no_gate = base.model_copy(deep=True)
    report = {
        "model_dir": args.model_dir, "backend": model.backend.name, "base_policy": base.version,
        "data": "data/intent/manifest.json (dev_cases, oos_dev, multi_dev, escalation_dev"
                + (", dev_independent" if args.independent else "") + "); data/benchmarks/ not read",
        "grid": grid, "constraints": {k: list(v) for k, v in CONSTRAINTS.items()},
        "selected_by_source": by_source,
        "base_policy_without_gate": evaluate(items, _with_disabled_gate(no_gate)),
        "selected": best,
        "top10": sorted(results, key=lambda r: (r["violation"], -r["metrics"]["dev_correct_draft_rate"]))[:10],
    }
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"backend {model.backend.name}; {len(results)} settings; feasible {best['n_feasible']}")
    print("base policy v2 without gate:", json.dumps({k: v for k, v in report['base_policy_without_gate'].items() if k != 'n'}))
    print("selected:", json.dumps(best["settings"]), "violation", best["violation"])
    print("metrics:", json.dumps({k: v for k, v in best["metrics"].items() if k != "n"}))
    for src, m in by_source.items():
        print(f"  {src}:", json.dumps({k: v for k, v in m.items() if k != "n"}))
    print(f"wrote {out.relative_to(REPO_ROOT).as_posix()}")
    if args.write_policy:
        policy = chosen
        data = json.loads(BASE_POLICY.read_text(encoding="utf-8"))
        data.update({
            "version": args.policy_version,
            "approved": False, "approved_by": None, "approval_date": None,
            "model_version": args.model_version,
            "tuning_report": args.out.replace("\\", "/"),
            "default_confidence_threshold": policy.default_confidence_threshold,
            "confidence_thresholds": policy.confidence_thresholds,
            "default_margin_threshold": policy.default_margin_threshold,
            "margin_thresholds": policy.margin_thresholds,
            "multi_request": policy.multi_request.model_dump(),
            "return_channel_guard": policy.return_channel_guard,
        })
        if policy.min_scope_probability is not None:
            data["min_scope_probability"] = policy.min_scope_probability
        target = REPO_ROOT / args.policy_out
        target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {target.relative_to(REPO_ROOT).as_posix()} (approved: false; approval is the team's)")
    return 0


def _with_disabled_gate(policy):
    policy.multi_request = MultiRequestPolicy(enabled=False, min_clause_confidence=1.0)
    return policy


if __name__ == "__main__":
    raise SystemExit(main())
