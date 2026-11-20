"""Tests for pipeline.evaluation.autoeval (offline; the model-backed test needs -m real_model)."""
import json
from pathlib import Path

import pytest

from pipeline.evaluation.autoeval import datasets as D
from pipeline.evaluation.autoeval import gates as G
from pipeline.evaluation.autoeval import llm_suite as L
from pipeline.evaluation.autoeval import metrics as M

REPO = Path(__file__).resolve().parents[2]
CONFIG = json.loads((REPO / "pipeline/configs/autoeval.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ metrics
def test_macro_f1_and_accuracy_match_hand_computation():
    gold = ["a", "a", "b", "b"]
    pred = ["a", "b", "b", "b"]
    assert M.accuracy(gold, pred) == 0.75
    # a: p=1 r=.5 f=.667 ; b: p=.667 r=1 f=.8
    assert M.macro_f1(gold, pred) == pytest.approx((2 / 3 + 0.8) / 2)


def test_ece_is_zero_for_perfectly_calibrated_bins():
    ece, table = M.expected_calibration_error([1.0, 1.0, 0.0, 0.0], [True, True, False, False])
    assert ece == pytest.approx(0.0)
    assert sum(r["n"] for r in table) == 4


def test_auroc_extremes():
    assert M.auroc([0.1, 0.2], [0.8, 0.9]) == 1.0
    assert M.auroc([0.8, 0.9], [0.1, 0.2]) == 0.0
    assert M.auroc([0.5], [0.5]) == 0.5


# ------------------------------------------------------------------ gates
def test_gates_pass_fail_warn_skip_and_not_run():
    results = {"ml": {"x": 0.95, "y": 3, "z": []}, "llm": {"live": {"skipped": True}}}
    gates = [
        {"id": "a", "metric": "ml.x", "op": ">=", "threshold": 0.9, "severity": "block"},
        {"id": "b", "metric": "ml.y", "op": "<=", "threshold": 1, "severity": "warn"},
        {"id": "c", "metric": "ml.y", "op": "<=", "threshold": 1, "severity": "block"},
        {"id": "d", "metric": "ml.z", "op": "empty", "threshold": None, "severity": "block"},
        {"id": "e", "metric": "llm.live.rate", "op": ">=", "threshold": 1, "severity": "block", "skip_if": "llm.live.skipped"},
        {"id": "f", "metric": "ml.missing", "op": ">=", "threshold": 1, "severity": "block"},
        {"id": "g", "metric": "other.v", "op": ">=", "threshold": 1, "severity": "block"},
    ]
    status = {g["id"]: g["status"] for g in G.evaluate(results, gates, {"ml", "llm"})}
    assert status == {"a": "pass", "b": "warn", "c": "fail", "d": "pass", "e": "skipped", "f": "not_run", "g": "not_run"}


def test_regression_respects_direction_and_tolerance():
    prev = {"ml": {"benchmark": {"macro_f1": 0.80, "calibration": {"ece": 0.05}}}}
    cur = {"ml": {"benchmark": {"macro_f1": 0.70, "calibration": {"ece": 0.06}}}}
    rows = {r["metric"]: r for r in G.regression(cur, prev, 0.02)}
    assert rows["ml.benchmark.macro_f1"]["regressed"] is True
    assert rows["ml.benchmark.calibration.ece"]["regressed"] is False


def test_every_configured_gate_is_well_formed():
    for g in CONFIG["gates"]:
        assert g["op"] in (">=", "<=", "==", ">", "<", "empty")
        assert g["severity"] in ("block", "warn")
        assert g["metric"].split(".")[0] in ("ml", "llm")


# ------------------------------------------------------------------ datasets
def test_noise_generation_is_deterministic():
    bench = D.load_jsonl(REPO / CONFIG["benchmark"])
    assert D.build_noise(bench, 42) == D.build_noise(bench, 42)
    assert D.build_noise(bench, 42) != D.build_noise(bench, 7)


def test_frozen_datasets_match_manifest():
    res = D.verify_manifest(CONFIG)
    assert res["ok"], res


def test_llm_cases_reference_existing_kb_documents():
    kb = L.load_kb(CONFIG)
    for c in D.load_jsonl(REPO / CONFIG["autoeval_dir"] / "llm_cases.jsonl"):
        assert c["evidence_doc_ids"] and all(i in kb for i in c["evidence_doc_ids"]), c["id"]
        assert c["expect"] in ("draft", "abstain", "draft_or_abstain")


# ------------------------------------------------------------------ LLM offline suite
def test_draft_analysis_flags_uncited_claims_numbers_and_commitments():
    sources = [{"source_id": "S1", "text": "Customers may return products within 30 days of receipt."}]
    a = L.analyse_draft("Returns are accepted within 30 days [S1]. Refunds arrive in 2 hours. "
                        "Your order has been cancelled [S1].", sources, {"S1"})
    assert a["claim_sentences"] == 3 and a["cited_sentences"] == 2
    assert a["unsupported_numbers"] == ["2"]
    assert a["commitments"]


def test_offline_response_has_case_insensitive_headers():
    assert L._Resp(503, {}).headers.get("retry-after") is None
    assert L._Resp(503, {}, headers={"Retry-After": "1"}).headers.get("retry-after") == "1"


def test_known_good_validator_behaviour_is_preserved():
    res = L.validator_probes(CONFIG, L.load_kb(CONFIG))
    broken_baseline = [p["id"] for p in res["probes"] if p["ref"] == "baseline" and not p["passed"]]
    assert broken_baseline == []


def test_redaction_and_privacy_probes_produce_reports():
    r = L.redaction_probes()
    assert r["n"] == len(L.REDACTION_PROBES)
    by_id = {p["id"]: p for p in r["probes"]}
    assert by_id["email"]["passed"] and by_id["phone_spaced"]["passed"]
    cases = D.load_jsonl(REPO / CONFIG["autoeval_dir"] / "llm_cases.jsonl")
    pp = L.payload_privacy(CONFIG, cases, L.load_kb(CONFIG), L.load_orders(CONFIG))
    assert pp["cases_checked"] > 0
    assert pp["pii_leaks"] == 0  # name / phone / email must never reach the provider


def test_live_mode_metrics_with_fake_provider(monkeypatch, tmp_path):
    class FakeClient:
        def __init__(self, api_key=None, model=None, http_client=None):
            self.model = model

        def generate(self, question, intent, evidence, business_context=None):
            from apps.core_backend.llm.gemini import prepare_llm_input
            if "secret" in question.lower() or "expired" in question.lower():
                raise L.LLMError("llm_insufficient_evidence")
            snap = prepare_llm_input(question, intent, evidence, business_context)
            s1 = snap["sources"][0]
            return {"body": "Per policy, see the details here [S1].", "input_snapshot": snap,
                    "citations": [{"source_id": "S1", "source_type": s1["source_type"], "document_id": s1["document_id"], "version": s1["version"]}],
                    "usage": {"promptTokenCount": 1000, "candidatesTokenCount": 100}}

        def close(self):
            pass

    monkeypatch.setattr(L, "GeminiDraftClient", FakeClient)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    cases = D.load_jsonl(REPO / CONFIG["autoeval_dir"] / "llm_cases.jsonl")
    res = L.live(CONFIG, cases, L.load_kb(CONFIG), L.load_orders(CONFIG), tmp_path, max_calls=200, log=lambda *_: None)
    assert res["skipped"] is False and res["calls"] == len(cases)
    assert res["draft_rate_when_expected"] == 1.0
    assert 0.0 < res["abstain_rate_when_expected"] < 1.0
    assert res["commitment_violations"] == 0
    assert res["cost_usd"] > 0
    assert (tmp_path / "llm_live_records.jsonl").exists()


def test_live_mode_skips_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    res = L.live(CONFIG, [], {}, {}, tmp_path, log=lambda *_: None)
    assert res == {"skipped": True, "reason": "GEMINI_API_KEY not set"}


# ------------------------------------------------------------------ real model (opt-in)
@pytest.mark.real_model
def test_ml_suite_runs_on_released_model():
    from pipeline.evaluation.autoeval import ml_suite
    model_dir = REPO / CONFIG["ml"]["model_dir"]
    if not (model_dir / "model.safetensors").exists():
        pytest.skip("released model not present locally")
    res = ml_suite.run(CONFIG, backend="numpy", log=lambda *_: None)
    assert res["model"]["ok"]
    assert res["benchmark"]["n_labeled"] > 100
    assert 0.0 <= res["oos"]["flagged_rate"] <= 1.0
