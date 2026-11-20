"""Frozen evaluation datasets: loading, hashing and deterministic (re)generation.

Generated files are committed under data/benchmarks/autoeval/v1 so every run measures exactly the
same inputs.  ``build`` regenerates them from the system benchmark + KB with a fixed seed and the
manifest records SHA-256 hashes; ``verify_manifest`` refuses silently edited datasets.
"""
from __future__ import annotations

import hashlib
import json
import random
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def load_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_text_file(path: Path) -> str:
    # Normalise line endings so Windows checkouts (CRLF) hash the same as Linux CI.
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


# --------------------------------------------------------------------------- noise
_CASUAL = {"please": "pls", "you": "u", "your": "ur", "are": "r", "what": "wat", "order": "ordr",
           "refund": "refnd", "package": "pkg", "thanks": "thx", "because": "bc", "my": "my"}


def _typo_word(word: str, rng: random.Random) -> str:
    i = rng.randrange(1, len(word) - 1)
    op = rng.choice(["swap", "drop", "dup"])
    if op == "swap":
        return word[:i] + word[i + 1] + word[i] + word[i + 2:]
    if op == "drop":
        return word[:i] + word[i + 1:]
    return word[:i] + word[i] + word[i:]


def make_typo(text: str, rng: random.Random, n_words: int = 2) -> str:
    words = text.split()
    idx = [i for i, w in enumerate(words) if len(w) >= 4 and w.isalpha()]
    for i in rng.sample(idx, min(n_words, len(idx))):
        words[i] = _typo_word(words[i], rng)
    return " ".join(words)


def make_casual(text: str) -> str:
    text = re.sub(r"[?.!,]", "", text.lower())
    return " ".join(_CASUAL.get(w, w) for w in text.split())


TYPO_VARIANTS = 3


def build_noise(benchmark: list[dict], seed: int) -> list[dict]:
    rows = []
    for case in benchmark:
        if case["primary_slice"] not in ("supported", "answerable") or not case.get("true_intent"):
            continue
        variants = [("clean", case["text"]), ("casual", make_casual(case["text"]))]
        # Several independent typo draws per case: a single draw makes the F1-drop estimate unstable.
        for k in range(TYPO_VARIANTS):
            variants.append((f"typo#{k}", make_typo(case["text"], random.Random(f"{seed}:{case['id']}:typo:{k}"))))
        for kind, text in variants:
            rows.append({"id": f"{case['id']}::{kind}", "source_id": case["id"], "kind": kind.split("#")[0], "text": text,
                         "true_intent": case["true_intent"], "context": case["context"]})
    return rows


# --------------------------------------------------------------------------- LLM cases
_MUST_MENTION = {
    "return_policy": r"30[\s-]*days?|thirty",
    "refund_policy": r"5\s*(?:to|-|–)\s*7",
    "cancel_order": r"courier|handed over|hand(?:ed)?[\s-]*over|before",
}
_INJECTION = re.compile(r"ignore all previous|override|<script|disregard", re.I)
_MUST_NOT = [r"(?i)system (?:prompt|instruction)", r"(?i)api[_ ]?key", r"(?i)password", r"<script", r"(?i)database dump"]


def _docs_for_intent(kb: list[dict], intent: str, limit: int = 3) -> list[str]:
    ids = [d["document_id"] for d in kb if intent in (d.get("supported_intents") or [])]
    return ids[:limit]


def build_llm_cases(benchmark: list[dict], kb: list[dict]) -> list[dict]:
    rows = []
    for c in benchmark:
        sl, intent, e = c["primary_slice"], c.get("true_intent"), c["expected"]
        base = {"id": c["id"], "text": c["text"], "intent": intent, "context": c["context"],
                "order_id": (c["context"].get("extracted_slots") or {}).get("order_id")}
        if sl == "answerable":
            rows.append({**base, "kind": "answerable", "expect": "draft",
                         "evidence_doc_ids": [g["doc_id"] for g in e["gold_sources"]],
                         "gold_doc_ids": [g["doc_id"] for g in e["gold_sources"]],
                         "must_mention": _MUST_MENTION.get(intent)})
        elif sl == "unanswerable":
            ev = _docs_for_intent(kb, intent) or [kb[0]["document_id"]]
            rows.append({**base, "kind": "unanswerable", "expect": "abstain", "evidence_doc_ids": ev, "gold_doc_ids": []})
        elif sl == "supported" and base["order_id"] and _docs_for_intent(kb, intent):
            rows.append({**base, "kind": "order_lookup", "expect": "draft",
                         "evidence_doc_ids": _docs_for_intent(kb, intent), "gold_doc_ids": _docs_for_intent(kb, intent)})
        elif sl == "uncertainty_and_faults" and _INJECTION.search(c["text"]) and intent:
            rows.append({**base, "kind": "injection", "expect": "draft_or_abstain",
                         "evidence_doc_ids": _docs_for_intent(kb, intent) or [kb[0]["document_id"]],
                         "gold_doc_ids": [], "must_not_match": _MUST_NOT})
    return rows


# --------------------------------------------------------------------------- manifest
def build(config: dict) -> dict:
    root = REPO_ROOT / config["autoeval_dir"]
    benchmark = load_jsonl(REPO_ROOT / config["benchmark"])
    kb = json.loads((REPO_ROOT / config["knowledge_base"]).read_text(encoding="utf-8"))
    write_jsonl(root / "ml_noise.jsonl", build_noise(benchmark, config["seed"]))
    write_jsonl(root / "llm_cases.jsonl", build_llm_cases(benchmark, kb))
    return write_manifest(config)


def tracked_files(config: dict) -> dict[str, Path]:
    root = REPO_ROOT / config["autoeval_dir"]
    return {
        "benchmark": REPO_ROOT / config["benchmark"],
        "knowledge_base": REPO_ROOT / config["knowledge_base"],
        "orders": REPO_ROOT / config["orders"],
        "ml_noise": root / "ml_noise.jsonl",
        "ml_oos": root / "ml_oos.jsonl",
        "llm_cases": root / "llm_cases.jsonl",
    }


def write_manifest(config: dict) -> dict:
    files = tracked_files(config)
    manifest = {"version": "autoeval-v1", "seed": config["seed"],
                "files": {k: {"path": str(p.relative_to(REPO_ROOT)).replace("\\", "/"), "sha256": sha256_text_file(p)}
                          for k, p in files.items()}}
    (REPO_ROOT / config["autoeval_dir"] / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(config: dict) -> dict[str, Any]:
    path = REPO_ROOT / config["autoeval_dir"] / "manifest.json"
    if not path.exists():
        return {"ok": False, "error": "manifest.json missing - run `autoeval build-data`"}
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mismatched = []
    for key, p in tracked_files(config).items():
        rec = manifest["files"].get(key)
        if rec is None or not p.exists() or sha256_text_file(p) != rec["sha256"]:
            mismatched.append(key)
    return {"ok": not mismatched, "mismatched": mismatched, "hashes": {k: v["sha256"][:12] for k, v in manifest["files"].items()}}
