"""Load the product-semantics intent data and guard it against leakage.

All files are ``synthetic-dev-only`` (DATA-03), labelled per docs/design/intent-label-definitions.md, and use
normalized placeholders such as ``[ORDER_ID]`` instead of identifiers (DATA-59). Pipe-separated, header
``intent|text``:
  * data/intent/train_supplement/v1/rows.synthetic-dev-only.psv -> extra training rows
  * data/intent/dev/v1/cases.synthetic-dev-only.psv              -> validation: calibration and tau/delta tuning

Out-of-domain texts (header ``category|text``) for outlier exposure: trained towards a uniform distribution
over the 46 labels, i.e. low confidence, without a 47th label:
  * data/intent/oos_train/v1/rows.synthetic-dev-only.psv -> training
  * data/intent/dev/v1/oos.synthetic-dev-only.psv        -> validation only

Multi-request dev cases (header ``kind|text``, kind ``multi`` or ``single``) tune the multi-request routing gate
(docs/design/multi-request-detection.md). ``single`` rows are single requests that contain a conjunction or two
sentences. Never used for training:
  * data/intent/dev_multi/v1/cases.synthetic-dev-only.psv

Escalation-boundary dev cases (header ``intent|text``): ``product_issue`` and channel returns (label definitions D2)
next to the supported intents they are confused with. Validation only:
  * data/intent/dev_escalation/v1/cases.synthetic-dev-only.psv

No file may resemble anything under data/benchmarks/ or another file (DATA-24, DATA-28). Benchmark texts are
compared but never printed: a hit reports only the benchmark file and line, so test items are not read.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

from pipeline.preparation.utils import STANDARD_INTENTS

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data/intent"
TRAIN_SUPPLEMENT = DATA_DIR / "train_supplement/v1/rows.synthetic-dev-only.psv"
# v2 = v1 plus rows for unsupported intents confused with draftable ones (docs/design/intent-model-v1.2.md).
TRAIN_SUPPLEMENT_V2 = DATA_DIR / "train_supplement/v2/rows.synthetic-dev-only.psv"
# v3 = v2 plus rows for patterns chosen from dev errors in round 5 (docs/design/intent-model-v1.2.md).
TRAIN_SUPPLEMENT_V3 = DATA_DIR / "train_supplement/v3/rows.synthetic-dev-only.psv"
DEV_SET = DATA_DIR / "dev/v1/cases.synthetic-dev-only.psv"
OOS_TRAIN = DATA_DIR / "oos_train/v1/rows.synthetic-dev-only.psv"
OOS_DEV = DATA_DIR / "dev/v1/oos.synthetic-dev-only.psv"
MULTI_DEV = DATA_DIR / "dev_multi/v1/cases.synthetic-dev-only.psv"
MULTI_KINDS = {"multi", "single"}
ESCALATION_DEV = DATA_DIR / "dev_escalation/v1/cases.synthetic-dev-only.psv"
# Written by an independent author (docs/design/intent-model-v1.2.md); development data, never training.
INDEPENDENT_DEV = DATA_DIR / "dev_independent/v1/cases.synthetic-dev-only.jsonl"
INDEPENDENT_KINDS = {"labelled", "oos", "multi"}
MANIFEST = DATA_DIR / "manifest.json"
OOS_CATEGORIES = {"general", "other_domain", "ecommerce_not_in_taxonomy", "vague"}
BENCHMARK_DIR = REPO_ROOT / "data/benchmarks"
# Short support questions share structure ("how long does X take"); 0.7 flags rewordings of the same
# sentence without flagging every question about the same topic.
NEAR_DUPLICATE_THRESHOLD = 0.7
_RAW_IDENTIFIER = re.compile(r"\bORD-?\d+\b|#\d{4,}\b", re.I)


def load_psv(path: str | Path, id_prefix: str, *, key: str = "intent", allowed: frozenset[str] | set[str] = STANDARD_INTENTS) -> pd.DataFrame:
    """Return a frame with ``sample_id``, ``instruction`` and ``key``; validates labels, duplicates, identifiers."""
    rows = []
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != f"{key}|text":
        raise ValueError(f"{path}: header must be '{key}|text'")
    for lineno, line in enumerate(lines[1:], start=2):
        if not line.strip():
            continue
        label, sep, text = line.partition("|")
        label, text = label.strip(), text.strip()
        if not sep or not text:
            raise ValueError(f"{path}:{lineno}: expected '{key}|text'")
        if label not in allowed:
            raise ValueError(f"{path}:{lineno}: unknown {key} {label!r}")
        if _RAW_IDENTIFIER.search(text):
            raise ValueError(f"{path}:{lineno}: raw identifier; use a placeholder such as [ORDER_ID] (DATA-59)")
        rows.append((label, text))
    df = pd.DataFrame(rows, columns=[key, "instruction"])
    dupes = df[df["instruction"].str.lower().duplicated(keep=False)]
    if not dupes.empty:
        raise ValueError(f"{path}: duplicate texts: {sorted(set(dupes['instruction']))[:5]}")
    df.insert(0, "sample_id", [f"{id_prefix}-{i:04d}" for i in range(len(df))])
    return df


def load_train_supplement(path: str | Path = TRAIN_SUPPLEMENT) -> pd.DataFrame:
    return load_psv(path, f"supp-{Path(path).parent.name}")


def load_dev_set(path: str | Path = DEV_SET) -> pd.DataFrame:
    return load_psv(path, "dev-v1")


def load_oos(path: str | Path, id_prefix: str) -> pd.DataFrame:
    return load_psv(path, id_prefix, key="category", allowed=OOS_CATEGORIES)


def load_oos_train(path: str | Path = OOS_TRAIN) -> pd.DataFrame:
    return load_oos(path, "oos-train-v1")


def load_oos_dev(path: str | Path = OOS_DEV) -> pd.DataFrame:
    return load_oos(path, "oos-dev-v1")


def load_multi_dev(path: str | Path = MULTI_DEV) -> pd.DataFrame:
    return load_psv(path, "multi-dev-v1", key="kind", allowed=MULTI_KINDS)



def load_escalation_dev(path: str | Path = ESCALATION_DEV) -> pd.DataFrame:
    return load_psv(path, "esc-dev-v1")


def load_independent_dev(path: str | Path = INDEPENDENT_DEV) -> list[dict]:
    """Rows ``{id, kind, true_intent, category, text}``; placeholders normalized as the classifier sees them."""
    from apps.ml_inference.preprocessing import normalize_placeholders

    rows, seen = [], set()
    for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        kind, label, text = row.get("kind"), row.get("true_intent"), row.get("text", "")
        if kind not in INDEPENDENT_KINDS:
            raise ValueError(f"{path}:{lineno}: unknown kind {kind!r}")
        if kind == "labelled" and label not in STANDARD_INTENTS:
            raise ValueError(f"{path}:{lineno}: unknown intent {label!r}")
        if _RAW_IDENTIFIER.search(text):
            raise ValueError(f"{path}:{lineno}: raw identifier; use a placeholder (DATA-59)")
        if text.lower() in seen:
            raise ValueError(f"{path}:{lineno}: duplicate text")
        seen.add(text.lower())
        rows.append({**row, "text": normalize_placeholders(text)})
    return rows


_NUMBER_RE = re.compile(r"\b(?:ord-?|#|no\.\s*)?\d[\d,.]*\b", re.I)


def normalise_tokens(text: str) -> frozenset[str]:
    text = _NUMBER_RE.sub(" <num> ", text.lower())
    return frozenset(re.findall(r"[a-z<>]+", text))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def find_near_duplicates(texts_a: list[str], labelled_b: list[tuple[str, str]], threshold: float = NEAR_DUPLICATE_THRESHOLD) -> list[tuple[str, str, float]]:
    """Pairs (text from A, label of the B item, score). ``labelled_b`` is (label, text); only the label is returned."""
    tokens_b = [(label, normalise_tokens(text)) for label, text in labelled_b]
    hits = []
    for a in texts_a:
        ta = normalise_tokens(a)
        for label, tb in tokens_b:
            score = jaccard(ta, tb)
            if score >= threshold:
                hits.append((a, label, round(score, 3)))
    return hits


def benchmark_texts(root: Path = BENCHMARK_DIR) -> list[tuple[str, str]]:
    """(``file:line``, text) for every ``text`` field of every JSONL file under data/benchmarks/."""
    items = []
    for path in sorted(root.rglob("*.jsonl")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if line.strip():
                row = json.loads(line)
                for key in ("text", "question", "query"):
                    if isinstance(row.get(key), str):
                        items.append((f"{rel}:{lineno}", row[key]))
    return items


def leakage_report(threshold: float = NEAR_DUPLICATE_THRESHOLD) -> dict[str, list[tuple[str, str, float]]]:
    train = load_train_supplement(TRAIN_SUPPLEMENT_V3)["instruction"].tolist() + load_oos_train()["instruction"].tolist()
    dev = (load_dev_set()["instruction"].tolist() + load_oos_dev()["instruction"].tolist()
           + load_multi_dev()["instruction"].tolist() + load_escalation_dev()["instruction"].tolist())
    if INDEPENDENT_DEV.exists():
        dev += [r["text"] for r in load_independent_dev()]
    bench = benchmark_texts()
    return {
        "train_vs_benchmark": find_near_duplicates(train, bench, threshold),
        "dev_vs_benchmark": find_near_duplicates(dev, bench, threshold),
        "dev_vs_train": find_near_duplicates(dev, [(t, t) for t in train], threshold),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build_manifest() -> dict:
    """Manifest per DATA-09: source, version, checksum, row count, producing process, creation date."""
    files = {
        "train_supplement": (TRAIN_SUPPLEMENT, load_train_supplement),
        "train_supplement_v2": (TRAIN_SUPPLEMENT_V2, lambda: load_train_supplement(TRAIN_SUPPLEMENT_V2)),
        "train_supplement_v3": (TRAIN_SUPPLEMENT_V3, lambda: load_train_supplement(TRAIN_SUPPLEMENT_V3)),
        "dev_cases": (DEV_SET, load_dev_set),
        "oos_train": (OOS_TRAIN, load_oos_train),
        "oos_dev": (OOS_DEV, load_oos_dev),
        "multi_dev": (MULTI_DEV, load_multi_dev),
        "escalation_dev": (ESCALATION_DEV, load_escalation_dev),
    }
    if INDEPENDENT_DEV.exists():
        files["independent_dev"] = (INDEPENDENT_DEV, load_independent_dev)
    return {
        "version": "v1",
        "classification": "synthetic-dev-only",
        "source": "Authored with AI assistance on 2026-11-06 per docs/design/intent-label-definitions.md; "
                  "identifiers replaced by normalized placeholders on 2026-11-12; 23 rows removed on 2026-11-12 "
                  "because they were near-duplicates (token Jaccard >= 0.7) of data/benchmarks/intent/v1 (DATA-24); 7 more removed on 2026-11-13 as near-duplicates of "
                  "data/benchmarks/intent/v2; multi_dev authored with AI assistance on 2026-11-13 per "
                  "docs/design/multi-request-detection.md without reading data/benchmarks/intent/v1; escalation_dev authored with AI assistance on 2026-11-13 for the "
                  "intents named by failed gate case IDs, without reading their texts",
        "producing_process": "hand-authored; validated by pipeline/preparation/intent_extra.py",
        "created": "2026-11-06",
        "files": {name: {"path": path.relative_to(REPO_ROOT).as_posix(), "sha256": _sha256(path), "rows": len(loader())}
                  for name, (path, loader) in files.items()},
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(description="Validate intent extra data, check leakage, write or verify the manifest.")
    ap.add_argument("--threshold", type=float, default=NEAR_DUPLICATE_THRESHOLD)
    ap.add_argument("--write-manifest", action="store_true")
    args = ap.parse_args()
    manifest = build_manifest()
    for name, info in manifest["files"].items():
        print(f"{name}: {info['rows']} rows  {info['path']}")
    if args.write_manifest:
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {MANIFEST.relative_to(REPO_ROOT).as_posix()}")
    elif MANIFEST.exists() and json.loads(MANIFEST.read_text(encoding="utf-8"))["files"] != manifest["files"]:
        print("manifest mismatch: files changed since data/intent/manifest.json was written")
        return 1
    report = leakage_report(args.threshold)
    for name, hits in report.items():
        print(f"{name}: {len(hits)} near-duplicates (jaccard >= {args.threshold})")
        for a, label, s in hits:
            print(f"  {s}  {a!r}  ~  {label}")
    return 1 if any(report.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
