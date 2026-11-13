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
    results = {"ml": {"x": 0.95, "y": 3, "z": [], "none_list": None}, "llm": {"live": {"skipped": True}}}
    gates = [
        {"id": "a", "metric": "ml.x", "op": ">=", "threshold": 0.9, "severity": "block"},
        {"id": "b", "metric": "ml.y", "op": "<=", "threshold": 1, "severity": "warn"},
        {"id": "c", "metric": "ml.y", "op": "<=", "threshold": 1, "severity": "block"},
        {"id": "d", "metric": "ml.z", "op": "empty", "threshold": None, "severity": "block"},
        {"id": "d_none", "metric": "ml.none_list", "op": "empty", "threshold": None, "severity": "block"},
        {"id": "e", "metric": "llm.live.rate", "op": ">=", "threshold": 1, "severity": "block", "skip_if": "llm.live.skipped"},
        {"id": "f", "metric": "ml.missing", "op": ">=", "threshold": 1, "severity": "block"},
        {"id": "f_warn", "metric": "ml.warn_missing", "op": ">=", "threshold": 1, "severity": "warn"},
        {"id": "g", "metric": "other.v", "op": ">=", "threshold": 1, "severity": "block"},
    ]
    status = {g["id"]: g["status"] for g in G.evaluate(results, gates, {"ml", "llm"})}
    assert status == {
        "a": "pass",
        "b": "warn",
        "c": "fail",
        "d": "pass",
        "d_none": "fail",
        "e": "skipped",
        "f": "fail",
        "f_warn": "not_run",
        "g": "not_run",
    }


def test_gates_preserve_offline_live_exclusion_and_fail_missing_live_blocking():
    gates = [
        {"id": "live_blk", "metric": "llm.live.draft_rate_when_expected", "op": ">=", "threshold": 0.9, "severity": "block", "skip_if": "llm.live.skipped"},
        {"id": "judge_adv", "metric": "llm.live.judge.grounded_rate", "op": ">=", "threshold": 0.9, "severity": "warn"},
        {"id": "off_blk", "metric": "llm.payload_privacy.pii_leaks", "op": "==", "threshold": 0, "severity": "block"},
    ]
    off_status = {g["id"]: g["status"] for g in G.evaluate({"llm": {"mode": "offline", "payload_privacy": {"pii_leaks": 0}}}, gates, {"llm"})}
    assert off_status == {"live_blk": "not_run", "judge_adv": "not_run", "off_blk": "pass"}

    live_missing = {g["id"]: g["status"] for g in G.evaluate({"llm": {"mode": "live", "payload_privacy": {"pii_leaks": 0}}}, gates, {"llm"})}
    assert live_missing == {"live_blk": "fail", "judge_adv": "not_run", "off_blk": "pass"}


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


def _make_temp_autoeval_env(tmp_path: Path) -> tuple[Path, Path]:
    from pipeline.evaluation.autoeval import cli as cli_mod  # noqa: F401
    data_dir = tmp_path / "data"
    autoeval_dir = tmp_path / "autoeval_data"
    out_dir = tmp_path / "out"
    data_dir.mkdir(parents=True)
    autoeval_dir.mkdir(parents=True)
    files = {
        "benchmark": data_dir / "bench.jsonl",
        "knowledge_base": data_dir / "kb.json",
        "orders": data_dir / "orders.json",
        "ml_noise": autoeval_dir / "ml_noise.jsonl",
        "ml_oos": autoeval_dir / "ml_oos.jsonl",
        "llm_cases": autoeval_dir / "llm_cases.jsonl",
    }
    for p in files.values():
        p.write_text("{}\n" if p.suffix == ".jsonl" else "[]\n", encoding="utf-8")
    manifest = {
        "version": "test",
        "seed": 42,
        "files": {k: {"path": str(p), "sha256": D.sha256_text_file(p)} for k, p in files.items()},
    }
    (autoeval_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    cfg = {
        "schema_version": 1,
        "seed": 42,
        "benchmark": str(files["benchmark"]),
        "knowledge_base": str(files["knowledge_base"]),
        "orders": str(files["orders"]),
        "autoeval_dir": str(autoeval_dir),
        "output_dir": str(out_dir),
        "regression_tolerance": 0.02,
        "gates": [
            {"id": "llm_pii", "metric": "llm.payload_privacy.pii_leaks", "op": "==", "threshold": 0, "severity": "block"},
            {"id": "llm_live", "metric": "llm.live.draft_rate_when_expected", "op": ">=", "threshold": 0.9, "severity": "block", "skip_if": "llm.live.skipped"},
            {"id": "llm_adv", "metric": "llm.live.judge.grounded_rate", "op": ">=", "threshold": 0.9, "severity": "warn"},
        ],
    }
    cfg_path = tmp_path / "autoeval.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return cfg_path, out_dir


def test_cli_rejects_empty_and_unknown_suite(tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    for bad in ("", "  ", "bogus", "llm,bogus"):
        rc = cli.main(["--config", str(cfg_path), "run", "--suite", bad, "--out", str(out_dir)])
        assert rc == 2


def test_cli_fails_closed_on_missing_and_malformed_compare(monkeypatch, tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    monkeypatch.setattr(L, "run", lambda *a, **kw: {"mode": "offline", "payload_privacy": {"pii_leaks": 0}})

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not-json", encoding="utf-8")
    no_results = tmp_path / "no_results.json"
    no_results.write_text(json.dumps({"summary": {"passed": True}}), encoding="utf-8")

    for compare_arg in (str(tmp_path / "missing.json"), str(bad_json), str(no_results)):
        rc = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--llm-mode", "offline", "--out", str(out_dir), "--compare", compare_arg])
        assert rc == 2
        assert not (out_dir / "latest.txt").exists()


def test_cli_fails_closed_on_changed_or_malformed_manifest(monkeypatch, tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    monkeypatch.setattr(L, "run", lambda *a, **kw: {"mode": "offline", "payload_privacy": {"pii_leaks": 0}})

    # Changed tracked file
    (tmp_path / "autoeval_data" / "llm_cases.jsonl").write_text('{"tampered": true}\n', encoding="utf-8")
    rc1 = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "drift"])
    assert rc1 == 2
    assert not (out_dir / "latest.txt").exists()

    # Corrupt manifest JSON
    (tmp_path / "autoeval_data" / "manifest.json").write_text("{corrupt", encoding="utf-8")
    rc2 = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "corrupt"])
    assert rc2 == 2
    err_files = list(out_dir.glob("*-corrupt/error.txt"))
    assert err_files and err_files[0].read_text(encoding="utf-8").strip()


def test_cli_fails_closed_on_missing_blocking_metric_and_all_not_run(monkeypatch, tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    # Missing required llm.payload_privacy.pii_leaks while llm is selected
    monkeypatch.setattr(L, "run", lambda *a, **kw: {"mode": "offline"})
    rc = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "missing-metric"])
    assert rc == 1
    latest = Path((out_dir / "latest.txt").read_text(encoding="utf-8").strip())
    rep = json.loads((latest / "report.json").read_text(encoding="utf-8"))
    assert rep["summary"]["passed"] is False
    assert rep["summary"]["fail"] == 1

    # Selected suite with zero passing gates (all not_run) must not report passed
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["gates"] = [{"id": "ml_only", "metric": "ml.model.ok", "op": "==", "threshold": True, "severity": "block"}]
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    rc_not_run = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "all-not-run"])
    assert rc_not_run == 1
    latest2 = Path((out_dir / "latest.txt").read_text(encoding="utf-8").strip())
    rep2 = json.loads((latest2 / "report.json").read_text(encoding="utf-8"))
    assert rep2["summary"]["passed"] is False
    assert rep2["summary"]["not_run"] == 1 and rep2["summary"]["pass"] == 0


def test_cli_runtime_failure_returns_code_2_and_redacts_secrets(monkeypatch, tmp_path: Path, capsys):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "AIza-super-secret-value")

    def boom(*a, **kw):
        raise RuntimeError("call failed https://u:dbsecret@host/db key=AIza-super-secret-value")

    monkeypatch.setattr(L, "run", boom)
    rc = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "boom"])
    assert rc == 2
    assert not (out_dir / "latest.txt").exists()
    err_txt = next(out_dir.glob("*-boom/error.txt")).read_text(encoding="utf-8")
    captured = capsys.readouterr()
    for text in (err_txt, captured.err):
        assert "AIza-super-secret-value" not in text
        assert "dbsecret" not in text
        assert "[REDACTED]" in text


def test_cli_external_out_dir_offline_run_succeeds_and_excludes_live(monkeypatch, tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    monkeypatch.setattr(L, "run", lambda *a, **kw: {"mode": "offline", "payload_privacy": {"pii_leaks": 0}})
    rc = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--llm-mode", "offline", "--out", str(out_dir), "--tag", "ok"])
    assert rc == 0
    run_dir = Path((out_dir / "latest.txt").read_text(encoding="utf-8").strip())
    assert (run_dir / "report.json").is_file() and (run_dir / "report.md").is_file()
    rep = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert rep["summary"]["passed"] is True
    assert rep["summary"]["not_run"] == 2  # llm_live + llm_adv excluded offline


def test_gates_do_not_skip_blocking_offline_pipeline_when_deps_missing():
    gates = [
        {"id": "pipe_blk", "metric": "llm.pipeline.blocking_failures", "op": "empty", "threshold": None, "severity": "block", "skip_if": "llm.pipeline.skipped"},
        {"id": "live_blk", "metric": "llm.live.draft_rate_when_expected", "op": ">=", "threshold": 0.9, "severity": "block", "skip_if": "llm.live.skipped"},
    ]
    res = {"llm": {"mode": "live", "pipeline": {"skipped": True, "reason": "No torch"}, "live": {"skipped": True}}}
    status = {g["id"]: g["status"] for g in G.evaluate(res, gates, {"llm"})}
    assert status == {"pipe_blk": "fail", "live_blk": "skipped"}


def test_cli_malformed_gate_op_and_type_mismatch_return_sanitized_code_2(monkeypatch, tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    monkeypatch.setattr(L, "run", lambda *a, **kw: {"mode": "offline", "payload_privacy": {"pii_leaks": "bad-type"}})

    # Type mismatch on numeric gate
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    cfg["gates"] = [{"id": "bad_type", "metric": "llm.payload_privacy.pii_leaks", "op": ">=", "threshold": 0, "severity": "block"}]
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    assert cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "bad-type"]) == 2
    assert not (out_dir / "latest.txt").exists()

    # Unknown gate op
    cfg["gates"] = [{"id": "bad_op", "metric": "llm.payload_privacy.pii_leaks", "op": "~=", "threshold": 0, "severity": "block"}]
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    assert cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--tag", "bad-op"]) == 2
    assert not (out_dir / "latest.txt").exists()


def test_cli_compare_without_overlapping_metrics_fails_closed(monkeypatch, tmp_path: Path):
    from pipeline.evaluation.autoeval import cli

    cfg_path, out_dir = _make_temp_autoeval_env(tmp_path)
    monkeypatch.setattr(L, "run", lambda *a, **kw: {"mode": "offline", "payload_privacy": {"pii_leaks": 0}})
    ml_only_baseline = tmp_path / "ml_only.json"
    ml_only_baseline.write_text(json.dumps({"results": {"ml": {"benchmark": {"accuracy": 0.9}}}}), encoding="utf-8")

    rc = cli.main(["--config", str(cfg_path), "run", "--suite", "llm", "--out", str(out_dir), "--compare", str(ml_only_baseline), "--tag", "no-overlap"])
    assert rc == 2
    assert not (out_dir / "latest.txt").exists()
    assert next(out_dir.glob("*-no-overlap/error.txt")).read_text(encoding="utf-8")


def test_pipeline_probes_reflect_actual_manual_fallback_and_draft_contract():
    res = L.pipeline_probes(CONFIG, L.load_kb(CONFIG))
    assert res["skipped"] is False
    assert res["blocking_failures"] == []
    by_id = {p["id"]: p for p in res["probes"]}
    assert by_id["draft_requires_human_approval"]["passed"] is True
    assert by_id["llm_failure_is_queued_for_staff"]["passed"] is True
    assert by_id["ml_failure_is_queued_for_staff"]["passed"] is True


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
