"""Regression tests for historical evaluation novelty reproducibility and UTF-8 BOM handling.

Covers the 4 required regression invariants:
1. Downstream result exports do not invalidate novelty.
2. Genuine pre-freeze overlap fails closed.
3. Missing or tampered inventory fails closed (HistoricalCorpusIntegrityError).
4. UTF-8 BOM and normal UTF-8 decode to identical semantic content without disk byte mutation.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from pipeline.evaluation.historical_inventory import (
    HistoricalCorpusIntegrityError,
    load_historical_corpus_inventory,
    read_json_safe,
    read_jsonl_safe,
    collect_historical_corpus_prompts,
    DEFAULT_INVENTORY_PATH,
    REPO_ROOT,
)
from artifacts.evaluation.fit2_independent_gate_20261113.gate import (
    historical_corpus,
    overlap_report,
    load_cases,
)


def test_downstream_result_export_does_not_invalidate_novelty(tmp_path: Path):
    """Downstream evaluation result exports containing holdout prompts must not pollute the antecedent corpus."""
    cases = load_cases()
    assert len(cases) == 36
    holdout_sample_text = cases[0]["text"]

    # Simulate a downstream candidate evaluation output directory containing holdout predictions
    downstream_dir = REPO_ROOT / "artifacts" / "evaluation" / "_temp_downstream_eval_regression_test"
    downstream_file = downstream_dir / "predictions_candidate.jsonl"
    try:
        downstream_dir.mkdir(parents=True, exist_ok=True)
        downstream_file.write_text(
            json.dumps({"id": "eval-01", "query": holdout_sample_text, "prediction": "cancel_order"}) + "\n",
            encoding="utf-8",
        )

        # Baseline historical corpus loader must ignore downstream evaluation exports not in historical inventory
        corpus, file_count = historical_corpus(roots=None)
        assert holdout_sample_text not in corpus

        rep = overlap_report(cases, corpus)
        assert rep["exact_overlap"] == [], f"Unexpected overlap introduced by downstream file: {rep['exact_overlap']}"
        assert rep["near_duplicates"] == [], f"Unexpected near-duplicates: {rep['near_duplicates']}"
    finally:
        if downstream_file.is_file():
            downstream_file.unlink()
        if downstream_dir.is_dir():
            downstream_dir.rmdir()


def test_prefreeze_overlap_fails_closed():
    """Injecting a genuine pre-freeze prompt must trigger exact overlap failure."""
    corpus, _ = historical_corpus(roots=None)
    assert len(corpus) > 0

    # Pick a known prompt from antecedent training/benchmark corpus
    antecedent_prompt = corpus[0]

    # Synthesize a candidate case copying the antecedent prompt
    leaked_case = [{"id": "synthetic-leak-01", "text": antecedent_prompt, "intent": "cancel_order"}]
    rep = overlap_report(leaked_case, corpus)

    assert rep["exact_overlap"] == ["synthetic-leak-01"], "Expected exact overlap failure on antecedent leak"


def test_tampered_or_missing_inventory_fails_closed(tmp_path: Path):
    """Missing or tampered inventory or files must raise HistoricalCorpusIntegrityError."""
    # Case 1: Missing inventory file
    missing_inv = tmp_path / "nonexistent_inventory.json"
    with pytest.raises(HistoricalCorpusIntegrityError, match="not found"):
        load_historical_corpus_inventory(inventory_path=missing_inv, repo_root=REPO_ROOT)

    # Case 2: Inventory points to a missing file
    fake_entry_inv = tmp_path / "tampered_missing_file_inventory.json"
    fake_entry_inv.write_text(
        json.dumps({
            "corpus_files": [
                {"path": "data/nonexistent_file_for_test.jsonl", "sha256": "0000000000000000000000000000000000000000000000000000000000000000"}
            ]
        }),
        encoding="utf-8",
    )
    with pytest.raises(HistoricalCorpusIntegrityError, match="Missing antecedent files"):
        load_historical_corpus_inventory(inventory_path=fake_entry_inv, repo_root=REPO_ROOT, verify_hashes=True)

    # Case 3: Inventory has mismatched sha256
    real_inv = read_json_safe(DEFAULT_INVENTORY_PATH)
    assert len(real_inv["corpus_files"]) > 0
    tampered_hash_inv = tmp_path / "tampered_hash_inventory.json"
    tampered_data = {
        "corpus_files": [
            {
                "path": real_inv["corpus_files"][0]["path"],
                "sha256": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
            }
        ]
    }
    tampered_hash_inv.write_text(json.dumps(tampered_data), encoding="utf-8")
    with pytest.raises(HistoricalCorpusIntegrityError, match="Mismatched antecedent file hashes"):
        load_historical_corpus_inventory(inventory_path=tampered_hash_inv, repo_root=REPO_ROOT, verify_hashes=True)


def test_utf8_bom_and_normal_utf8_semantic_equivalence(tmp_path: Path):
    """JSON and JSONL with BOM decode to identical Python objects as UTF-8 without modifying disk bytes."""
    payload = {
        "id": "item-101",
        "description": "Thanh toán đơn hàng qua thẻ",
        "nested": {"score": 0.985, "tags": ["tiếng việt", "hỗ trợ"]},
    }
    raw_utf8 = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    bom_utf8 = b"\xef\xbb\xbf" + raw_utf8

    json_plain = tmp_path / "plain.json"
    json_bom = tmp_path / "with_bom.json"
    json_plain.write_bytes(raw_utf8)
    json_bom.write_bytes(bom_utf8)

    # Test JSON decoding
    decoded_plain = read_json_safe(json_plain)
    decoded_bom = read_json_safe(json_bom)
    assert decoded_plain == decoded_bom == payload

    # Disk bytes must remain unaltered
    assert json_bom.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not json_plain.read_bytes().startswith(b"\xef\xbb\xbf")

    # Test JSONL decoding
    line_payload = [{"line": 1, "text": "Hủy đơn hàng"}, {"line": 2, "text": "Hoàn tiền giao dịch"}]
    raw_jsonl_bytes = "\n".join(json.dumps(row, ensure_ascii=False) for row in line_payload).encode("utf-8")
    bom_jsonl_bytes = b"\xef\xbb\xbf" + raw_jsonl_bytes

    jsonl_plain = tmp_path / "plain.jsonl"
    jsonl_bom = tmp_path / "with_bom.jsonl"
    jsonl_plain.write_bytes(raw_jsonl_bytes)
    jsonl_bom.write_bytes(bom_jsonl_bytes)

    decoded_jsonl_plain = read_jsonl_safe(jsonl_plain)
    decoded_jsonl_bom = read_jsonl_safe(jsonl_bom)
    assert decoded_jsonl_plain == decoded_jsonl_bom == line_payload

    # Disk bytes must remain unaltered
    assert jsonl_bom.read_bytes().startswith(b"\xef\xbb\xbf")
    assert not jsonl_plain.read_bytes().startswith(b"\xef\xbb\xbf")


def test_gate_historical_corpus_propagates_integrity_violation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The public gate.historical_corpus() entry point must propagate HistoricalCorpusIntegrityError fail-closed."""
    import pipeline.evaluation.historical_inventory as inv_mod

    # Case 1: Missing inventory file must raise HistoricalCorpusIntegrityError without falling back
    monkeypatch.setattr(inv_mod, "DEFAULT_INVENTORY_PATH", tmp_path / "missing_inventory.json")
    with pytest.raises(HistoricalCorpusIntegrityError, match="not found"):
        historical_corpus()

    # Case 2: Tampered hash in inventory must raise HistoricalCorpusIntegrityError without falling back
    tampered_inv = tmp_path / "tampered_hash_inventory.json"
    tampered_inv.write_text(
        json.dumps({
            "corpus_files": [
                {"path": "data/knowledge/approved_kb.v2.json", "sha256": "0" * 64}
            ]
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(inv_mod, "DEFAULT_INVENTORY_PATH", tampered_inv)
    with pytest.raises(HistoricalCorpusIntegrityError, match="integrity violation"):
        historical_corpus()

