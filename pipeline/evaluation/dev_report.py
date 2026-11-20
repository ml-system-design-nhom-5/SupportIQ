"""Milestone report for an intent model and routing policy on development data only (docs/design/intent-model-v1.2.md).

Reads the data/intent dev files (own and independent) and never data/benchmarks/ (DATA-25). Reports the routing
metrics of ``tune_routing.evaluate`` per source and overall, the noisy-text Macro-F1 drop on the independent
labelled rows (deterministic noise from the autoeval builder), and whether every milestone target is met.

    python -m pipeline.evaluation.dev_report --model-dir artifacts/models/trained/<model> \
        --policy apps/core_backend/config/policies/intent_policy.v4.json --out artifacts/training/<run>/dev_report.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from apps.core_backend.intent.routing import SUPPORTED_12_INTENTS, load_policy_v2
from pipeline.evaluation.autoeval import metrics as M
from pipeline.evaluation.autoeval.backends import IntentModel, load_model_dirs
from pipeline.evaluation.autoeval.datasets import build_noise
from pipeline.evaluation.tune_routing import evaluate, load_items
from pipeline.preparation.intent_extra import load_independent_dev

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGETS = {  # metric: (op, bound)
    "dev_must_escalate_drafted": ("==", 0),
    "dev_macro_f1": (">=", 0.78),
    "oos_flag_rate": (">=", 0.92),
    "dev_clarify_rate": ("<=", 0.15),
    "dev_confident_error_rate": ("<=", 0.02),
    "noise_f1_drop": ("<=", 0.08),
}


def noise_drop(model: IntentModel, seed: int = 42) -> dict:
    cases = [{"id": r["id"], "text": r["text"], "true_intent": r["true_intent"], "context": {},
              "primary_slice": "supported" if r["true_intent"] in SUPPORTED_12_INTENTS else "unsupported"}
             for r in load_independent_dev() if r["kind"] == "labelled"]
    by_kind: dict[str, list[tuple[str, str]]] = {}
    for row in build_noise(cases, seed):
        by_kind.setdefault(row["kind"], []).append((row["true_intent"], model.predict(row["text"], record_latency=False)["intent"]))
    f1 = {k: M.macro_f1([g for g, _ in v], [p for _, p in v]) for k, v in by_kind.items()}
    drops = {k: round(f1["clean"] - f1[k], 4) for k in f1 if k != "clean"}
    return {"macro_f1": {k: round(v, 4) for k, v in f1.items()}, "drop": drops, "max_drop": max(drops.values())}


def check(metrics: dict) -> dict:
    out = {}
    for name, (op, bound) in TARGETS.items():
        v = metrics.get(name)
        ok = v is not None and (v == bound if op == "==" else v >= bound if op == ">=" else v <= bound)
        out[name] = {"value": v, "target": f"{op} {bound}", "met": ok}
    return out


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model-dir", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--backend", default="auto", choices=["auto", "torch", "numpy"])
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    policy = load_policy_v2(str(REPO_ROOT / args.policy))
    policy.approved = True  # development measurement of the candidate policy, not an approval
    mr = policy.multi_request
    grid = {"min_words": [mr.min_words if mr else 3], "request_clauses_only": [bool(mr and mr.request_clauses_only)]}
    model = IntentModel(load_model_dirs(args.model_dir, REPO_ROOT, args.backend))
    items = load_items(model, grid, independent=True)
    report = {"model_dir": args.model_dir, "policy": args.policy, "policy_version": policy.version,
              "backend": model.backend.name, "data": "data/intent dev files; data/benchmarks/ not read"}
    for name, subset in (("all", items), ("independent", [i for i in items if i["source"] == "independent"]),
                         ("own", [i for i in items if i["source"] == "own"])):
        report[name] = evaluate(subset, policy)
    report["noise_independent"] = noise_drop(model)
    for name in ("all", "independent"):
        report[name]["noise_f1_drop"] = report["noise_independent"]["max_drop"]
        report[f"targets_{name}"] = check(report[name])
    report["milestone_met"] = all(t["met"] for n in ("all", "independent") for t in report[f"targets_{n}"].values())
    out = REPO_ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    for name in ("all", "independent"):
        print(name, json.dumps({k: v["value"] for k, v in report[f"targets_{name}"].items()}),
              "missed:", [k for k, v in report[f"targets_{name}"].items() if not v["met"]])
    print("milestone met:", report["milestone_met"], "| wrote", out.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
