"""Guards for the product-semantics intent data (dev set, supplementary rows, out-of-domain texts)."""
import json

import pytest

from pipeline.preparation import intent_extra as X
from pipeline.preparation.utils import CORE_PRODUCT_INTENTS


def test_files_load_with_valid_labels_and_stable_ids():
    train, dev = X.load_train_supplement(), X.load_dev_set()
    assert len(train) >= 500 and len(dev) >= 150
    assert train["sample_id"].iloc[0] == "supp-v1-0000"
    assert dev["sample_id"].iloc[0] == "dev-v1-0000"
    assert set(CORE_PRODUCT_INTENTS) <= set(train["intent"])
    assert set(CORE_PRODUCT_INTENTS) <= set(dev["intent"])


def test_files_are_marked_synthetic_dev_only():
    for path in (X.TRAIN_SUPPLEMENT, X.DEV_SET, X.OOS_TRAIN, X.OOS_DEV):
        assert "synthetic-dev-only" in path.name


def test_manifest_matches_files():
    stored = json.loads(X.MANIFEST.read_text(encoding="utf-8"))
    assert stored["classification"] == "synthetic-dev-only"
    assert stored["files"] == X.build_manifest()["files"]


def test_no_leakage_into_benchmarks_or_between_dev_and_train():
    report = X.leakage_report()
    assert report == {"train_vs_benchmark": [], "dev_vs_benchmark": [], "dev_vs_train": []}


def test_benchmark_hits_report_location_not_text():
    items = X.benchmark_texts()
    assert len(items) >= 156
    assert all(":" in location for location, _ in items)
    hits = X.find_near_duplicates(["where is my order now"], [("bench.jsonl:7", "Where is my order now?")])
    assert hits == [("where is my order now", "bench.jsonl:7", 1.0)]


def test_normalisation_ignores_order_ids_and_case():
    assert X.normalise_tokens("Where is ORD-1001?") == X.normalise_tokens("where is #48213")


def test_loader_rejects_unknown_intent_duplicates_and_raw_identifiers(tmp_path):
    bad = tmp_path / "bad.psv"
    bad.write_text("intent|text\nnot_an_intent|hello\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown intent"):
        X.load_psv(bad, "t")
    dup = tmp_path / "dup.psv"
    dup.write_text("intent|text\ntrack_order|Where is it?\ntrack_order|where is it?\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        X.load_psv(dup, "t")
    raw = tmp_path / "raw.psv"
    raw.write_text("intent|text\ntrack_order|Where is ORD-1001?\n", encoding="utf-8")
    with pytest.raises(ValueError, match="DATA-59"):
        X.load_psv(raw, "t")
