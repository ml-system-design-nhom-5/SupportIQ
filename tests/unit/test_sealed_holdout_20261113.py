"""Focused integrity, zero-overlap, and KB-provenance checks for sealed 72-case holdout."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from pipeline.evaluation.classifier_acceptance_gate import (
    SUPPORTED_12_INTENTS,
    compute_file_sha256,
    load_jsonl,
    normalize_text,
    token_set,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
HOLDOUT_DIR = REPO_ROOT / "artifacts/evaluation/sealed_holdout_20261113"
HOLDOUT_CASES_PATH = HOLDOUT_DIR / "sealed_holdout_cases.jsonl"
HOLDOUT_MANIFEST_PATH = HOLDOUT_DIR / "sealed_holdout_manifest.json"


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def collect_historical_prompts(repo_root: Path = REPO_ROOT) -> list[tuple[str, str]]:
    """Collect seen benchmark and prior evaluation prompts across the workspace."""
    from pipeline.evaluation.historical_inventory import collect_historical_prompt_tuples
    return collect_historical_prompt_tuples(repo_root=repo_root, exclude_dirs=[HOLDOUT_DIR])

    seen: list[tuple[str, str]] = []

    def _walk(obj: Any, source: str) -> None:
        if isinstance(obj, dict):
            for key in ("text", "query", "instruction", "message", "user_query"):
                val = obj.get(key)
                if isinstance(val, str) and len(val.strip()) >= 8:
                    seen.append((source, val.strip()))
            for val in obj.values():
                if isinstance(val, (dict, list)):
                    _walk(val, source)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, source)

    for rel in ("data/benchmarks", "artifacts/evaluation"):
        base = repo_root / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or any("sealed_holdout" in part for part in path.parts):
                continue
            if path.suffix == ".jsonl":
                for line in path.read_text(encoding="utf-8-sig").splitlines():
                    if line.strip():
                        _walk(json.loads(line), str(path.relative_to(repo_root)))
            elif path.suffix == ".json" and path.stat().st_size < 2_000_000:
                _walk(json.loads(path.read_text(encoding="utf-8-sig")), str(path.relative_to(repo_root)))
    return seen


def active_kb_doc_keys(repo_root: Path = REPO_ROOT) -> set[str]:
    release = json.loads((repo_root / "apps/ai_service/kb-release.json").read_text(encoding="utf-8-sig"))
    kb = json.loads((repo_root / "data/knowledge/approved_kb.v2.json").read_text(encoding="utf-8-sig"))
    kb_keys = {f"{d['document_id']}:{d['version']}" for d in kb if d.get("status") == "approved"}
    rel_keys = {f"{d['document_id']}:{d['version']}" for d in release["documents"]}
    return kb_keys & rel_keys


def test_sealed_holdout_counts_kb_and_zero_overlap() -> None:
    rows = load_jsonl(HOLDOUT_CASES_PATH)
    assert len(rows) == 72

    slices = Counter(r["slice"] for r in rows)
    assert slices == {
        "supported_answerable": 24,
        "novel_ood": 24,
        "mandatory_escalation_compound": 24,
    }

    sup_rows = [r for r in rows if r["slice"] == "supported_answerable"]
    sup_intents = Counter(r["true_intent"] for r in sup_rows)
    assert set(sup_intents.keys()) == set(SUPPORTED_12_INTENTS)
    assert all(count == 2 for count in sup_intents.values())

    active_docs = active_kb_doc_keys()
    for row in rows:
        for doc_ref in row["expected_docs"]:
            assert doc_ref in active_docs, f"{row['id']} cites unknown/inactive doc {doc_ref}"
        if row["slice"] == "supported_answerable":
            if row["true_intent"] == "human_agent":
                assert row["expected_actions"] == ["escalate"]
                assert row["must_escalate"] is True
                assert row["must_not_draft"] is True
                assert row["expected_docs"] == []
            else:
                assert row["expected_actions"] == ["retrieve_draft"]
                assert row["must_not_draft"] is False
                assert len(row["expected_docs"]) >= 1
        elif row["slice"] == "novel_ood":
            assert row["must_not_draft"] is True
            assert "retrieve_draft" not in row["expected_actions"]
        else:
            assert row["expected_actions"] == ["escalate"]
            assert row["must_escalate"] is True
            assert row["must_not_draft"] is True

    # Zero self-overlap
    for idx, left in enumerate(rows):
        lnorm = normalize_text(left["text"])
        ltok = token_set(left["text"])
        for right in rows[idx + 1 :]:
            assert lnorm != normalize_text(right["text"]), f"Duplicate holdout text: {left['id']} vs {right['id']}"
            assert _jaccard(ltok, token_set(right["text"])) < 0.70, f"Near-dup holdout: {left['id']} vs {right['id']}"

    # Zero exact or high-Jaccard overlap against all historical prompts
    historical = collect_historical_prompts()
    hist_norms = {normalize_text(txt): (src, txt) for src, txt in historical}
    hist_toks = [(src, txt, token_set(txt)) for src, txt in historical]
    for row in rows:
        rnorm = normalize_text(row["text"])
        rtok = token_set(row["text"])
        assert rnorm not in hist_norms, f"{row['id']} exact match with {hist_norms[rnorm][0]}"
        for src, txt, htok in hist_toks:
            j = _jaccard(rtok, htok)
            assert j < 0.70, f"{row['id']} Jaccard={j:.3f} vs {src}: {txt!r}"

    if HOLDOUT_MANIFEST_PATH.exists():
        manifest = json.loads(HOLDOUT_MANIFEST_PATH.read_text(encoding="utf-8"))
        assert manifest["cases_sha256"] == compute_file_sha256(HOLDOUT_CASES_PATH)
        assert manifest["total_cases"] == 72
