"""Build the frozen intent scenario set (ADR-0016) in the autoeval format, without printing any message.

Input: ``data/benchmarks/intent/v1/raw_cases.jsonl``, written by an independent author (see ``AUTHORING.md`` there):
messages and labels only. Everything else is derived mechanically from the label, with the rules of
``data/benchmarks/system/v1``:

* supported intent (not ``human_agent``): may draft or clarify; ``human_agent`` and the 34 unsupported intents
  must escalate to the team in ``INTENT_TO_QUEUE_MAP``;
* a message with an order placeholder gets the verified order scope and the ``order_id`` slot;
* out-of-scope messages must be flagged or escalated;
* noisy variants come from ``datasets.build_noise`` with the configured seed (never written by hand).

Outputs next to the input: ``cases.jsonl`` (ML benchmark), ``ml_oos.jsonl``, ``ml_noise.jsonl``, ``manifest.json``.
Reports print counts only, so whoever trains or tunes the model never reads the items (ADR-0016).
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from apps.core_backend.intent.routing import INTENT_TO_QUEUE_MAP, SUPPORTED_12_INTENTS

from .datasets import REPO_ROOT, build_noise, load_jsonl, sha256_text_file, write_jsonl

SET_DIR = REPO_ROOT / "data/benchmarks/intent/v1"
OOS_CATEGORIES = {"general", "other_domain", "ecommerce_not_in_taxonomy", "vague", "multi_intent"}
OUTPUTS = ("cases.jsonl", "ml_oos.jsonl", "ml_noise.jsonl")
TRACKED = ("raw_cases.jsonl", "AUTHORING.md") + OUTPUTS


def _context(has_order: bool) -> dict:
    if has_order:
        return {"ticket_customer_id": "demo-customer", "verified_scope": "ticket:read order:read",
                "is_personal_lookup": True, "extracted_slots": {"order_id": "[ORDER_ID_1]"}}
    return {"ticket_customer_id": "demo-customer", "verified_scope": "ticket:read",
            "is_personal_lookup": False, "extracted_slots": {}}


def _expected(intent: str) -> dict:
    escalate = intent == "human_agent" or intent not in SUPPORTED_12_INTENTS
    return {"actions": ["escalate"] if escalate else ["retrieve_draft", "clarify"],
            "team": INTENT_TO_QUEUE_MAP[intent], "must_escalate": escalate, "must_not_draft": escalate}


def build(raw_rows: list[dict], seed: int) -> dict[str, list[dict]]:
    cases, oos = [], []
    for row in raw_rows:
        slice_, intent = row["slice"], row.get("true_intent")
        has_order = bool(row.get("has_order_reference"))
        tags = ["placeholder"] if has_order else []
        if slice_ in ("supported", "unsupported"):
            if intent not in INTENT_TO_QUEUE_MAP or (slice_ == "supported") != (intent in SUPPORTED_12_INTENTS):
                raise ValueError(f"{row['id']}: label {intent!r} does not match slice {slice_!r}")
            cases.append({"id": row["id"], "primary_slice": slice_, "tags": tags, "text": row["text"],
                          "true_intent": intent, "context": _context(has_order), "expected": _expected(intent),
                          "fault": None})
        elif slice_ == "out_of_scope":
            if row.get("category") not in OOS_CATEGORIES:
                raise ValueError(f"{row['id']}: unknown out-of-scope category")
            oos.append({"id": row["id"], "category": row["category"], "text": row["text"], "true_intent": intent,
                        "context": _context(has_order), "expected": "flag_or_escalate"})
        else:
            raise ValueError(f"{row['id']}: unknown slice {slice_!r}")
    return {"cases.jsonl": cases, "ml_oos.jsonl": oos, "ml_noise.jsonl": build_noise(cases, seed)}


def write_manifest(set_dir: Path, seed: int, author: str) -> dict:
    manifest = {"version": f"intent-{set_dir.name}", "adr": "docs/decisions/0016-frozen-intent-scenario-set.md", "seed": seed,
                "author": author,
                "counts": {name: len(load_jsonl(set_dir / name)) for name in ("raw_cases.jsonl",) + OUTPUTS},
                "files": {name: sha256_text_file(set_dir / name) for name in TRACKED}}
    (set_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(set_dir: Path) -> dict:
    path = set_dir / "manifest.json"
    if not path.exists():
        return {"ok": False, "error": f"{path} missing"}
    files = json.loads(path.read_text(encoding="utf-8"))["files"]
    mismatched = [name for name, digest in files.items()
                  if not (set_dir / name).exists() or sha256_text_file(set_dir / name) != digest]
    return {"ok": not mismatched, "mismatched": mismatched}


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set-dir", default=str(SET_DIR))
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--author", default="independent AI agent session (see AUTHORING.md)",
                    help="who wrote raw_cases.jsonl and when; stored in the manifest")
    args = ap.parse_args(argv)
    set_dir = Path(args.set_dir)
    if (set_dir / "manifest.json").exists():
        print("refusing to rebuild: the set is frozen once its manifest exists (DATA-23)")
        return 2
    outputs = build(load_jsonl(set_dir / "raw_cases.jsonl"), args.seed)
    for name, rows in outputs.items():
        write_jsonl(set_dir / name, rows)
    manifest = write_manifest(set_dir, args.seed, args.author)
    print(json.dumps(manifest["counts"]))
    cases = outputs["cases.jsonl"]
    print(json.dumps({"by_slice": Counter(c["primary_slice"] for c in cases),
                      "must_escalate": sum(c["expected"]["must_escalate"] for c in cases),
                      "with_placeholder": sum("placeholder" in c["tags"] for c in cases),
                      "oos_by_category": Counter(o["category"] for o in outputs["ml_oos.jsonl"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
