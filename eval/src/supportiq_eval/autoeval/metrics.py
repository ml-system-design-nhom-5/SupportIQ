"""Dependency-light metric helpers (numpy only) used by the automatic evaluation suites."""
from __future__ import annotations

from typing import Iterable, Sequence

import numpy as np


def accuracy(gold: Sequence[str], pred: Sequence[str]) -> float | None:
    if not gold:
        return None
    return float(np.mean([g == p for g, p in zip(gold, pred)]))


def macro_f1(gold: Sequence[str], pred: Sequence[str], labels: Iterable[str] | None = None) -> float | None:
    """Macro-F1 over `labels` (default: labels present in gold), zero_division=0."""
    if not gold:
        return None
    labels = sorted(set(gold)) if labels is None else list(labels)
    scores = []
    for lab in labels:
        tp = sum(1 for g, p in zip(gold, pred) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred) if g == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        scores.append(2 * prec * rec / (prec + rec) if prec + rec else 0.0)
    return float(np.mean(scores))


def per_class_f1(gold: Sequence[str], pred: Sequence[str]) -> dict[str, dict]:
    out = {}
    for lab in sorted(set(gold) | set(pred)):
        tp = sum(1 for g, p in zip(gold, pred) if g == lab and p == lab)
        fp = sum(1 for g, p in zip(gold, pred) if g != lab and p == lab)
        fn = sum(1 for g, p in zip(gold, pred) if g == lab and p != lab)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        out[lab] = {"support": tp + fn, "precision": round(prec, 4), "recall": round(rec, 4),
                    "f1": round(2 * prec * rec / (prec + rec), 4) if prec + rec else 0.0}
    return out


def expected_calibration_error(conf: Sequence[float], correct: Sequence[bool], n_bins: int = 10) -> tuple[float | None, list[dict]]:
    """Equal-width ECE plus the reliability table."""
    if not conf:
        return None, []
    c = np.asarray(conf, dtype=float)
    y = np.asarray(correct, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    ece, table = 0.0, []
    for i, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        k = (c >= lo) & ((c < hi) if i < n_bins - 1 else (c <= hi))
        if not k.any():
            continue
        acc, mc = float(y[k].mean()), float(c[k].mean())
        ece += k.sum() / len(c) * abs(acc - mc)
        table.append({"bin": f"[{lo:.1f},{hi:.1f}{']' if i == n_bins - 1 else ')'}", "n": int(k.sum()),
                      "accuracy": round(acc, 4), "mean_confidence": round(mc, 4)})
    return float(ece), table


def auroc(scores_negative: Sequence[float], scores_positive: Sequence[float]) -> float | None:
    """Probability that a random positive scores higher than a random negative (ties = 0.5)."""
    if not scores_negative or not scores_positive:
        return None
    neg = np.asarray(scores_negative, dtype=float)
    pos = np.asarray(scores_positive, dtype=float)
    gt = (pos[:, None] > neg[None, :]).sum()
    eq = (pos[:, None] == neg[None, :]).sum()
    return float((gt + 0.5 * eq) / (len(pos) * len(neg)))


def percentile(values: Sequence[float], q: float) -> float | None:
    if not values:
        return None
    return float(np.percentile(np.asarray(values, dtype=float), q))


def rate(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def selective_accuracy(conf: Sequence[float], correct: Sequence[bool], thresholds=(0.5, 0.6, 0.7, 0.8, 0.9)) -> list[dict]:
    c = np.asarray(conf, dtype=float)
    y = np.asarray(correct, dtype=bool)
    rows = []
    for t in thresholds:
        k = c >= t
        rows.append({"threshold": t, "coverage": round(float(k.mean()), 4) if len(c) else None,
                     "accuracy": round(float(y[k].mean()), 4) if k.any() else None})
    return rows
