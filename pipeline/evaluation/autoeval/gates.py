"""Acceptance gates and run-to-run regression checks."""
from __future__ import annotations

from typing import Any

_MISSING = object()


def get_path(results: dict, dotted: str):
    cur: Any = results
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _compare(value, op: str, threshold) -> bool:
    if op == "empty":
        return not value
    if value is None:
        return False
    return {">=": value >= threshold, "<=": value <= threshold, "==": value == threshold,
            ">": value > threshold, "<": value < threshold}[op]


def evaluate(results: dict, gates: list[dict], suites: set[str]) -> list[dict]:
    out = []
    for g in gates:
        suite = g["metric"].split(".", 1)[0]
        row = {k: g.get(k) for k in ("id", "metric", "op", "threshold", "severity", "ref", "desc")}
        if suite not in suites:
            row.update(status="not_run", value=None)
        elif g.get("skip_if") and get_path(results, g["skip_if"]) is True:
            row.update(status="skipped", value=None)
        else:
            v = get_path(results, g["metric"])
            if v is _MISSING:
                row.update(status="not_run", value=None)
            else:
                row.update(value=v, status="pass" if _compare(v, g["op"], g["threshold"]) else
                           ("fail" if g["severity"] == "block" else "warn"))
        out.append(row)
    return out


# metric -> True if higher is better
REGRESSION_METRICS = {
    "ml.benchmark.accuracy": True, "ml.benchmark.macro_f1": True, "ml.benchmark.scope_accuracy": True,
    "ml.benchmark.team_accuracy": True, "ml.benchmark.calibration.ece": False, "ml.noise.max_f1_drop": False,
    "ml.oos.flagged_rate": True, "ml.oos.low_conf_rate": True, "ml.benchmark.routing.clarify_rate_on_draftable": False,
    "llm.validator.pass_rate": True, "llm.redaction.pass_rate": True,
    "llm.live.draft_rate_when_expected": True, "llm.live.abstain_rate_when_expected": True,
    "llm.live.citation_sentence_coverage": True, "llm.live.gold_source_cited_rate": True,
    "llm.live.latency_p95_s": False, "llm.live.judge.grounded_rate": True,
}


def regression(current: dict, previous: dict, tolerance: float) -> list[dict]:
    rows = []
    for metric, higher_better in REGRESSION_METRICS.items():
        a, b = get_path(previous, metric), get_path(current, metric)
        if a is _MISSING or b is _MISSING or a is None or b is None:
            continue
        delta = b - a
        worse = (-delta if higher_better else delta) > tolerance
        rows.append({"metric": metric, "previous": a, "current": b, "delta": delta, "regressed": worse})
    return rows
