"""Fit2 independent gate helpers: holdout integrity/overlap + manifest (`python gate.py manifest`)."""
from __future__ import annotations

import csv
import difflib
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CASES = HERE / "cases.jsonl"
MANIFEST = HERE / "manifest.json"
SUPPORTED_12 = ["track_order", "cancel_order", "delivery_time", "delivery_issue", "shipping_costs", "return_policy",
                "return_product", "refund_policy", "request_refund", "refund_status", "payment_issue", "human_agent"]
TEXT_KEYS = ("text", "query", "instruction", "message", "user_query")
ROOT_ARTIFACTS = Path(r"F:\Năm 3\SD\project\SupportIQ\artifacts")  # read-only extra corpus (Bitext review rows, audits)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t.lower())).strip()


def toks(t: str) -> set[str]:
    return set(norm(t).split())


def load_cases() -> list[dict]:
    return [json.loads(x) for x in CASES.read_text(encoding="utf-8").splitlines() if x.strip()]


def _walk(o, out):
    if isinstance(o, dict):
        for k in TEXT_KEYS:
            v = o.get(k)
            if isinstance(v, str) and len(v.strip()) >= 8:
                out.append(v.strip())
        for v in o.values():
            if isinstance(v, (dict, list)):
                _walk(v, out)
    elif isinstance(o, list):
        for i in o:
            _walk(i, out)


def historical_corpus(roots: list[Path] | None = None) -> tuple[list[str], int]:
    """All prompts from prior datasets/benchmarks (old sealed72 included, own dir excluded).

    When roots is None, uses the immutable historical as-of inventory (commit 16b01eb)
    to prevent downstream evaluation prediction exports from invalidating novelty.
    """
    if roots is None:
        from pipeline.evaluation.historical_inventory import collect_historical_corpus_prompts
        return collect_historical_corpus_prompts(exclude_dirs=[HERE])

    roots = roots or [REPO / "data", REPO / "artifacts/evaluation", ROOT_ARTIFACTS / "preparation", ROOT_ARTIFACTS / "audit"]
    out: list[str] = []
    files = 0
    for base in roots:
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or HERE in p.parents or p.stat().st_size > 50_000_000:
                continue
            try:
                if p.suffix == ".jsonl":
                    for ln in p.read_text(encoding="utf-8-sig").splitlines():
                        if ln.strip():
                            _walk(json.loads(ln), out)
                elif p.suffix == ".json":
                    _walk(json.loads(p.read_text(encoding="utf-8-sig")), out)
                elif p.suffix == ".csv":
                    with p.open(encoding="utf-8-sig", newline="") as f:
                        for row in csv.DictReader(f):
                            _walk(row, out)
                else:
                    continue
                files += 1
            except (UnicodeDecodeError, json.JSONDecodeError, csv.Error):
                continue
    return out, files


def overlap_report(rows: list[dict], corpus: list[str]) -> dict:
    """Exact, token-Jaccard and char-sequence near-duplicate scan against corpus; also internal."""
    cn = {norm(t) for t in corpus}
    ct = [(t, toks(t)) for t in set(corpus)]
    exact, near, worst = [], [], []
    for r in rows:
        n, tk = norm(r["text"]), toks(r["text"])
        if n in cn:
            exact.append(r["id"])
        best = (0.0, 0.0, "")
        for t, ts in ct:
            if not ts:
                continue
            j = len(tk & ts) / len(tk | ts)
            if j >= 0.40:
                s = difflib.SequenceMatcher(None, n, norm(t)).ratio()
            else:
                s = 0.0
            if j > best[0] or (j == best[0] and s > best[1]):
                best = (j, s, t)
        worst.append({"id": r["id"], "max_jaccard": round(best[0], 3), "max_seq_ratio": round(best[1], 3)})
        if best[0] >= 0.70 or best[1] >= 0.85:
            near.append({"id": r["id"], "jaccard": round(best[0], 3), "seq": round(best[1], 3), "match": best[2]})
    internal = [(a["id"], b["id"]) for i, a in enumerate(rows) for b in rows[i + 1:]
                if norm(a["text"]) == norm(b["text"]) or len(toks(a["text"]) & toks(b["text"])) / len(toks(a["text"]) | toks(b["text"])) >= 0.70]
    return {"exact_overlap": exact, "near_duplicates": near, "internal_duplicates": internal,
            "max_jaccard_overall": max(w["max_jaccard"] for w in worst), "max_seq_overall": max(w["max_seq_ratio"] for w in worst)}


def build_manifest() -> dict:
    rows = load_cases()
    corpus, files = historical_corpus()
    ov = overlap_report(rows, corpus)
    assert not ov["exact_overlap"] and not ov["near_duplicates"] and not ov["internal_duplicates"], ov
    kb = REPO / "data/knowledge/approved_kb.v2.json"
    return {
        "holdout_id": "fit2_independent_gate_20261113", "status": "LOCKED_PRE_CANDIDATE",
        "cases_file": "artifacts/evaluation/fit2_independent_gate_20261113/cases.jsonl", "cases_sha256": sha256(CASES),
        "total_cases": len(rows), "slice_counts": dict(Counter(r["slice"] for r in rows)),
        "subgroup_counts": dict(Counter(f"{r['slice']}/{r['subgroup']}" for r in rows)),
        "supported_intents": dict(Counter(r["true_intent"] for r in rows if r["slice"] == "supported")),
        "as_of": sorted({r["context"]["as_of"] for r in rows}),
        "active_kb_release": "current-policies-v1", "approved_kb_sha256": sha256(kb),
        "kb_release_sha256": sha256(REPO / "apps/ai_service/kb-release.json"),
        "intent_policy_sha256": sha256(REPO / "apps/core_backend/config/policies/intent_policy.v2.json"),
        "overlap_corpus_prompts": len(corpus), "overlap_corpus_files": files,
        "overlap_thresholds": {"token_jaccard_lt": 0.70, "char_seq_ratio_lt": 0.85},
        "max_jaccard_vs_history": ov["max_jaccard_overall"], "max_seq_ratio_vs_history": ov["max_seq_overall"],
        "visibility_rule": "Prompts/gold withheld from A and B until final candidate lock; only manifest/hash/count shared.",
    }


if __name__ == "__main__" and sys.argv[1:] == ["manifest"]:
    MANIFEST.write_text(json.dumps(build_manifest(), indent=2) + "\n", encoding="utf-8")
    print(MANIFEST.read_text(encoding="utf-8"))
