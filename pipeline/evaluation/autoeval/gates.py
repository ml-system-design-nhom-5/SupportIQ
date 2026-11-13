"""Acceptance gates and run-to-run regression checks."""
from __future__ import annotations

from typing import Any

_MISSING = object()
_VALID_OPS = {">=", "<=", "==", ">", "<", "empty"}
_ORDER_OPS = {">=", "<=", ">", "<"}


def get_path(results: dict, dotted: str):
    cur: Any = results
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _validate_gate(g: Any) -> tuple[str, str, str]:
    if not isinstance(g, dict):
        raise ValueError("gate entry must be an object")
    metric = g.get("metric")
    op = g.get("op")
    severity = g.get("severity")
    if not isinstance(metric, str) or "." not in metric:
        raise ValueError(f"invalid gate metric: {metric!r}")
    if not isinstance(op, str) or op not in _VALID_OPS:
        raise ValueError(f"unsupported gate op {op!r} for {g.get('id') or metric!r}")
    if severity not in ("block", "warn"):
        raise ValueError(f"invalid gate severity {severity!r} for {g.get('id') or metric!r}")
    if op in _ORDER_OPS:
        thresh = g.get("threshold")
        if isinstance(thresh, bool) or not isinstance(thresh, (int, float)):
            raise TypeError(f"gate {g.get('id') or metric!r} op {op!r} requires numeric threshold, got {thresh!r}")
    return metric, op, severity


def _compare(value, op: str, threshold) -> bool:
    if op not in _VALID_OPS:
        raise ValueError(f"unsupported gate op {op!r}")
    if value is None:
        return False
    if op == "empty":
        return not value
    if op == "==":
        return value == threshold
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"op {op!r} requires numeric value, got {type(value).__name__}")
    return {">=": value >= threshold, "<=": value <= threshold,
            ">": value > threshold, "<": value < threshold}[op]


def evaluate(results: dict, gates: list[dict], suites: set[str]) -> list[dict]:
    out = []
    llm_offline = get_path(results, "llm.mode") == "offline"
    for g in gates:
        metric, op, severity = _validate_gate(g)
        suite = metric.split(".", 1)[0]
        row = {k: g.get(k) for k in ("id", "metric", "op", "threshold", "severity", "ref", "desc")}
        # Blocking offline/pipeline gates must fail closed if dependencies are missing; only live scope can skip_if.
        allow_skip = metric.startswith("llm.live.") or severity != "block"
        if suite not in suites:
            row.update(status="not_run", value=None)
        elif allow_skip and g.get("skip_if") and get_path(results, g["skip_if"]) is True:
            row.update(status="skipped", value=None)
        elif suite == "llm" and llm_offline and metric.startswith("llm.live."):
            row.update(status="not_run", value=None)
        else:
            v = get_path(results, metric)
            if v is _MISSING:
                row.update(status="fail" if severity == "block" else "not_run", value=None)
            else:
                row.update(value=v, status="pass" if _compare(v, op, g["threshold"]) else
                           ("fail" if severity == "block" else "warn"))
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
