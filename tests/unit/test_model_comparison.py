"""Unit tests for Transformer and Baseline Comparison benchmark."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from pipeline.evaluation import EvaluationError
from pipeline.preparation.utils import compute_sha256, save_json
from pipeline.training.artifacts import IntentModelBundle
from tests.unit.test_evaluation_ml import make_eval_fixture


def make_comparison_fixture(tmp_path: Path) -> dict[str, Any]:
    """Create a complete comparison fixture with 3 baselines and 2 mock transformers."""
    fx = make_eval_fixture(tmp_path)
    eval_dir = tmp_path / "artifacts" / "evaluation" / "03-11-2026-00"
    eval_dir.mkdir(parents=True, exist_ok=True)

    test_df = fx.root / "artifacts" / "preparation" / "03-11-2026-00" / "cleaned.csv"
    splits_df = fx.root / "artifacts" / "preparation" / "03-11-2026-00" / "split_assignments.csv"
    c_df = pd.read_csv(test_df)
    s_df = pd.read_csv(splits_df)
    m_test = c_df.merge(s_df[s_df["partition"] == "test"], on="sample_id")

    eval_outputs: dict[str, str] = {}
    models = ["linear_svm", "logistic_regression", "multinomial_nb"]

    for mid in models:
        mdir = eval_dir / "intent" / mid
        mdir.mkdir(parents=True, exist_ok=True)

        preds_rows = []
        for _, row in m_test.iterrows():
            preds_rows.append({
                "sample_id": row["sample_id"],
                "y_true": row["intent"],
                "y_pred": row["intent"],
            })
        preds_df = pd.DataFrame(preds_rows)
        preds_file = mdir / "predictions.csv"
        preds_df.to_csv(preds_file, index=False)
        eval_outputs[f"intent/{mid}/predictions.csv"] = compute_sha256(preds_file)

        metrics_file = mdir / "metrics.json"
        save_json({"macro_f1": 1.0, "accuracy": 1.0}, metrics_file)
        eval_outputs[f"intent/{mid}/metrics.json"] = compute_sha256(metrics_file)

    eval_manifest_data = {
        "schema_version": 1,
        "mode": "ml",
        "run_id": "03-11-2026-00",
        "status": "completed",
        "inputs": {
            "training_manifest": compute_sha256(fx.train_manifest),
            "preparation_manifest": compute_sha256(fx.prep_manifest),
            "cleaned_csv": compute_sha256(fx.cleaned_csv),
            "split_assignments": compute_sha256(fx.splits_csv),
            "split_report": compute_sha256(fx.split_report),
        },
        "outputs": eval_outputs,
        "winner_locked": {
            "candidate_id": "linear_svm__v1",
            "model_id": "linear_svm",
            "cv_macro_f1": 0.99,
            "test_macro_f1": 1.0,
        },
    }
    eval_manifest = eval_dir / "manifest.json"
    save_json(eval_manifest_data, eval_manifest)

    # Setup mock transformer directories
    models_dir = tmp_path / "artifacts" / "models"
    siq_dir = models_dir / "trained" / "distilbert-supportiq"
    sp_dir = models_dir / "finetuned" / "supportpilot-distilbert"
    siq_dir.mkdir(parents=True, exist_ok=True)
    sp_dir.mkdir(parents=True, exist_ok=True)

    intents = sorted(m_test["intent"].unique())
    id2label = {str(i): c for i, c in enumerate(intents)}
    label2id = {c: i for i, c in enumerate(intents)}

    for t_dir in (siq_dir, sp_dir):
        save_json({
            "architectures": ["DistilBertForSequenceClassification"],
            "id2label": id2label,
            "label2id": label2id,
        }, t_dir / "config.json")
        save_json({"model_max_length": 64}, t_dir / "tokenizer_config.json")
        save_json({"version": "1.0"}, t_dir / "tokenizer.json")
        (t_dir / "model.safetensors").write_bytes(b"mock_safetensors_binary_data_for_test")

    save_json({"training_samples": 9200}, siq_dir / "training_report.json")

    config = {
        "schema_version": 1,
        "seed": 42,
        "timing": {
            "warmup_requests": 2,
            "benchmark_requests": 5,
            "latency_batch_size": 1,
            "throughput_batch_size": 4,
        },
        "device": "cpu",
        "num_threads": 2,
        "max_length": 64,
        "n_folds": 2,
        "expected_intents": intents,
        "baseline_training_manifest": str(fx.train_manifest),
        "historical_evaluation_manifest": str(eval_manifest),
        "models": {
            "multinomial_nb": {"type": "baseline"},
            "logistic_regression": {"type": "baseline"},
            "linear_svm": {"type": "baseline"},
            "supportiq_distilbert": {
                "type": "transformer",
                "model_dir": str(siq_dir),
                "provenance": {
                    "origin": "local_finetuned",
                    "base_model": "distilbert/distilbert-base-uncased",
                    "membership_evidence": None,
                },
            },
            "supportpilot_distilbert": {
                "type": "transformer",
                "model_dir": str(sp_dir),
                "provenance": {
                    "origin": "external_finetuned",
                    "base_model": "distilbert/distilbert-base-uncased",
                    "membership_evidence": None,
                },
            },
        },
    }

    return {
        "fx": fx,
        "eval_manifest": eval_manifest,
        "siq_dir": siq_dir,
        "sp_dir": sp_dir,
        "config": config,
    }


def test_historical_test_ids_match_exactly(tmp_path):
    from pipeline.evaluation.comparison_contracts import verify_comparison_inputs

    setup = make_comparison_fixture(tmp_path)
    cfg = setup["config"]

    # 1. Missing test ID in predictions
    eval_dir = setup["eval_manifest"].parent
    preds_path = eval_dir / "intent" / "linear_svm" / "predictions.csv"
    df = pd.read_csv(preds_path)
    df_short = df.iloc[:-1]  # drop one sample
    df_short.to_csv(preds_path, index=False)
    # update hash in manifest
    m = json.loads(setup["eval_manifest"].read_text(encoding="utf-8"))
    m["outputs"]["intent/linear_svm/predictions.csv"] = compute_sha256(preds_path)
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)sample.*id|missing|mismatch"):
        verify_comparison_inputs(cfg, tmp_path)

    # 2. Duplicate test ID
    df_dup = pd.concat([df, df.iloc[0:1]], ignore_index=True)
    df_dup.to_csv(preds_path, index=False)
    m["outputs"]["intent/linear_svm/predictions.csv"] = compute_sha256(preds_path)
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)duplicate"):
        verify_comparison_inputs(cfg, tmp_path)

    # 3. Matching IDs but mismatched y_true
    df_tampered = df.copy()
    df_tampered.loc[0, "y_true"] = "wrong_intent_label"
    df_tampered.to_csv(preds_path, index=False)
    m["outputs"]["intent/linear_svm/predictions.csv"] = compute_sha256(preds_path)
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)y_true|label mismatch"):
        verify_comparison_inputs(cfg, tmp_path)


def test_model_and_split_hashes_must_match_history(tmp_path):
    from pipeline.evaluation.comparison_contracts import verify_comparison_inputs

    setup = make_comparison_fixture(tmp_path)
    cfg = setup["config"]
    m = json.loads(setup["eval_manifest"].read_text(encoding="utf-8"))

    # Tamper cleaned_csv hash in historical manifest
    m["inputs"]["cleaned_csv"] = "A" * 64
    setup["eval_manifest"].write_text(json.dumps(m), encoding="utf-8")

    with pytest.raises(EvaluationError, match="(?i)hash mismatch"):
        verify_comparison_inputs(cfg, tmp_path)


def test_missing_provenance_is_explicit_not_verified(tmp_path):
    from pipeline.evaluation.comparison_contracts import verify_comparison_inputs

    setup = make_comparison_fixture(tmp_path)
    cfg = setup["config"]

    verified = verify_comparison_inputs(cfg, tmp_path)
    specs = verified["transformer_specs"]

    for model_id in ("supportiq_distilbert", "supportpilot_distilbert"):
        assert model_id in specs
        reg = specs[model_id]["provenance"]
        assert reg["status"] == "unverified"
        assert reg["eligible_for_independent_ranking"] is False


# =========================================================================
# Task 2: Adapter Tests
# =========================================================================

class MockHFConfig:
    def __init__(self, id2label: dict[int | str, str], label2id: dict[str, int] | None = None):
        self.id2label = {int(k): v for k, v in id2label.items()}
        self.label2id = label2id or {v: int(k) for k, v in id2label.items()}
        self.architectures = ["DistilBertForSequenceClassification"]


class MockHFModel:
    def __init__(self, config: MockHFConfig, fake_logits: np.ndarray | None = None):
        self.config = config
        self.training = False
        self._fake_logits = fake_logits
        self.call_count = 0

    def eval(self):
        self.training = False
        return self

    def to(self, device):
        return self

    def __call__(self, input_ids=None, attention_mask=None):
        import torch
        self.call_count += 1
        assert not torch.is_grad_enabled(), "Prediction must run under inference/no_grad mode"
        batch_size = input_ids.shape[0] if input_ids is not None else 1
        num_classes = len(self.config.id2label)
        if self._fake_logits is not None:
            logits = torch.tensor(self._fake_logits, dtype=torch.float32)
        else:
            logits = torch.zeros((batch_size, num_classes), dtype=torch.float32)
        return type("Output", (), {"logits": logits})()


class MockTokenizer:
    def __init__(self):
        self.call_count = 0

    def __call__(self, texts, **kwargs):
        import torch
        self.call_count += 1
        batch_size = len(texts)
        max_len = kwargs.get("max_length", 64)
        return {
            "input_ids": torch.ones((batch_size, min(max_len, 10)), dtype=torch.long),
            "attention_mask": torch.ones((batch_size, min(max_len, 10)), dtype=torch.long),
        }


def test_adapter_maps_reordered_hf_labels(monkeypatch, tmp_path):
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    # id2label is deliberately inverted relative to alphabetical:
    # 0 -> "track_order", 1 -> "cancel_order"
    hf_config = MockHFConfig(id2label={0: "track_order", 1: "cancel_order"})
    # fake logits: for sample 0, index 1 has higher score -> should predict "cancel_order"
    fake_logits = np.array([[0.1, 2.5]])
    mock_model = MockHFModel(hf_config, fake_logits=fake_logits)
    mock_tok = MockTokenizer()

    monkeypatch.setattr(
        "transformers.AutoTokenizer.from_pretrained",
        lambda *args, **kwargs: mock_tok,
    )
    monkeypatch.setattr(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        lambda *args, **kwargs: (mock_model, {"missing_keys": []}),
    )

    adapter = TransformerIntentAdapter(
        model_dir=tmp_path,
        model_id="test_adapter",
        max_length=64,
        device="cpu",
    )

    preds = adapter.predict(["I want to cancel"])
    assert len(preds) == 1
    assert preds[0] == "cancel_order"


@pytest.mark.parametrize("bad_id2label, match_err", [
    ({0: "LABEL_0", 1: "LABEL_1"}, "LABEL_"),
    ({0: "track_order", 2: "cancel_order"}, "contiguous|missing index"),
    ({0: "track_order", 1: "track_order"}, "duplicate"),
])
def test_adapter_rejects_invalid_hf_taxonomies(monkeypatch, tmp_path, bad_id2label, match_err):
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    hf_config = MockHFConfig(id2label=bad_id2label)
    mock_model = MockHFModel(hf_config)
    mock_tok = MockTokenizer()

    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *args, **kwargs: mock_tok)
    monkeypatch.setattr(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        lambda *args, **kwargs: (mock_model, {"missing_keys": []}),
    )

    with pytest.raises(EvaluationError, match=f"(?i){match_err}"):
        TransformerIntentAdapter(model_dir=tmp_path, model_id="test_adapter")


def test_inference_never_initializes_random_head(monkeypatch, tmp_path):
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    hf_config = MockHFConfig(id2label={0: "a", 1: "b"})
    mock_model = MockHFModel(hf_config)
    mock_tok = MockTokenizer()

    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *args, **kwargs: mock_tok)
    # Simulate missing classifier weights in checkpoint
    monkeypatch.setattr(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        lambda *args, **kwargs: (mock_model, {"missing_keys": ["classifier.weight", "classifier.bias"]}),
    )

    with pytest.raises(EvaluationError, match="(?i)missing.*classifier.*weights"):
        TransformerIntentAdapter(model_dir=tmp_path, model_id="test_adapter")


def test_adapter_uses_eval_inference_and_local_files(monkeypatch, tmp_path):
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    hf_config = MockHFConfig(id2label={0: "a", 1: "b"})
    mock_model = MockHFModel(hf_config)
    mock_tok = MockTokenizer()

    captured_kwargs = {}

    def capture_loader(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return (mock_model, {"missing_keys": []})

    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *args, **kwargs: mock_tok)
    monkeypatch.setattr("transformers.AutoModelForSequenceClassification.from_pretrained", capture_loader)

    adapter = TransformerIntentAdapter(model_dir=tmp_path, model_id="test_adapter", device="cpu")
    assert captured_kwargs.get("local_files_only") is True
    assert captured_kwargs.get("trust_remote_code") is False

    preds = adapter.predict(["hello"])
    assert mock_model.training is False
    assert len(preds) == 1


def test_empty_input_returns_empty_without_model_call(monkeypatch, tmp_path):
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    hf_config = MockHFConfig(id2label={0: "a", 1: "b"})
    mock_model = MockHFModel(hf_config)
    mock_tok = MockTokenizer()

    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *args, **kwargs: mock_tok)
    monkeypatch.setattr(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        lambda *args, **kwargs: (mock_model, {"missing_keys": []}),
    )

    adapter = TransformerIntentAdapter(model_dir=tmp_path, model_id="test_adapter")
    res = adapter.predict([])
    assert len(res) == 0
    assert mock_model.call_count == 0

    probs = adapter.predict_proba([])
    assert probs.shape == (0, 2)
    assert mock_model.call_count == 0


def test_probability_columns_match_classes(monkeypatch, tmp_path):
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    # id2label: 0 -> "beta", 1 -> "alpha"
    # classes_ should be sorted: ["alpha", "beta"]
    hf_config = MockHFConfig(id2label={0: "beta", 1: "alpha"})
    fake_logits = np.array([[1.0, 3.0]])  # higher for index 1 ("alpha")
    mock_model = MockHFModel(hf_config, fake_logits=fake_logits)
    mock_tok = MockTokenizer()

    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *args, **kwargs: mock_tok)
    monkeypatch.setattr(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        lambda *args, **kwargs: (mock_model, {"missing_keys": []}),
    )

    adapter = TransformerIntentAdapter(model_dir=tmp_path, model_id="test_adapter")
    assert adapter.classes_ == ["alpha", "beta"]

    probs = adapter.predict_proba(["test text"])
    assert probs.shape == (1, 2)
    # Column 0 corresponds to adapter.classes_[0] == "alpha" (which had logit 3.0)
    # Column 1 corresponds to adapter.classes_[1] == "beta" (which had logit 1.0)
    assert probs[0, 0] > probs[0, 1]
    assert np.isclose(probs.sum(axis=1)[0], 1.0)


# =========================================================================
# Task 3: Benchmark & Hardware Tests
# =========================================================================

def test_latency_protocol_is_identical_for_all_models():
    from pipeline.evaluation.benchmark import benchmark_classifier

    texts = ["query 1", "query 2", "query 3"]
    cfg = {
        "timing": {
            "warmup_requests": 2,
            "benchmark_requests": 4,
            "latency_batch_size": 1,
            "throughput_batch_size": 3,
        }
    }

    call_log = []

    class MockBundle:
        def predict(self, batch):
            call_log.append(list(batch))
            return np.array(["track_order"] * len(batch))

    bundle = MockBundle()
    t = [0.0]

    def fake_clock():
        t[0] += 0.001
        return t[0]

    res = benchmark_classifier(bundle, texts, cfg, clock=fake_clock)
    assert res["latency"]["requests_measured"] == 4
    assert len(res["latency"]["durations_seconds"]) == 4
    # Check that warmup (2) + benchmark (4) were all batch_size=1
    for call in call_log[:6]:
        assert len(call) == 1
    # Check throughput call was batch_size=3
    assert len(call_log[6]) == 3


def test_gpu_sync_brackets_timed_prediction():
    from pipeline.evaluation.benchmark import benchmark_classifier

    sync_events = []

    class SyncBundle:
        def predict(self, batch):
            sync_events.append("predict")
            return np.array(["track_order"] * len(batch))

        def synchronize(self):
            sync_events.append("sync")

    bundle = SyncBundle()
    cfg = {
        "timing": {
            "warmup_requests": 1,
            "benchmark_requests": 1,
            "latency_batch_size": 1,
            "throughput_batch_size": 1,
        }
    }

    t = [0.0]

    def fake_clock():
        sync_events.append("clock")
        t[0] += 0.001
        return t[0]

    benchmark_classifier(bundle, ["query"], cfg, clock=fake_clock)

    # For timed latency prediction, the sequence must bracket predict with sync:
    # sync -> clock(t0) -> predict -> sync -> clock(t1)
    # Let's locate the benchmark slice after warmup
    assert "sync" in sync_events
    predict_idx = sync_events.index("predict")
    # Verify sync occurs before clock(t0) and before clock(t1)
    assert sync_events.count("sync") >= 2


def test_no_silent_cpu_fallback(monkeypatch, tmp_path):
    import torch
    from pipeline.evaluation.transformer_adapter import TransformerIntentAdapter

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    with pytest.raises(EvaluationError, match="(?i)cuda.*available"):
        TransformerIntentAdapter(model_dir=tmp_path, model_id="test_cuda", device="cuda")


def test_zero_or_negative_duration_raises_evaluation_error():
    from pipeline.evaluation.benchmark import benchmark_classifier

    class DummyBundle:
        def predict(self, batch):
            return np.array(["track_order"] * len(batch))

    cfg = {
        "timing": {
            "warmup_requests": 1,
            "benchmark_requests": 2,
            "latency_batch_size": 1,
            "throughput_batch_size": 2,
        }
    }

    # Clock goes backwards: t1 < t0
    t = [10.0]

    def backward_clock():
        t[0] -= 1.0
        return t[0]

    with pytest.raises(EvaluationError, match="(?i)invalid duration"):
        benchmark_classifier(DummyBundle(), ["query"], cfg, clock=backward_clock)


# =========================================================================
# Task 4: Comparison Runner Tests
# =========================================================================

def _setup_mock_transformers_for_runner(monkeypatch, setup):
    """Helper to mock transformers so real weights are not loaded during runner tests."""
    intents = setup["config"]["expected_intents"]
    id2label = {i: c for i, c in enumerate(intents)}
    hf_config = MockHFConfig(id2label=id2label)
    mock_model = MockHFModel(hf_config)
    mock_tok = MockTokenizer()

    monkeypatch.setattr("transformers.AutoTokenizer.from_pretrained", lambda *args, **kwargs: mock_tok)
    monkeypatch.setattr(
        "transformers.AutoModelForSequenceClassification.from_pretrained",
        lambda *args, **kwargs: (mock_model, {"missing_keys": []}),
    )


def test_comparison_has_five_rows_and_keeps_cv_winner(monkeypatch, tmp_path):
    from pipeline.evaluation.run_comparison import run_comparison

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    report_data = run_comparison(
        config_path=cfg_file,
        run_id="03-11-2026-cmp-test",
        repo_root=tmp_path,
        output_root=out_root,
    )

    run_dir = out_root / "03-11-2026-cmp-test"
    cmp_csv = run_dir / "comparison.csv"
    assert cmp_csv.exists()

    df = pd.read_csv(cmp_csv)
    assert len(df) == 5
    assert set(df["model_id"]) == {
        "multinomial_nb",
        "logistic_regression",
        "linear_svm",
        "supportiq_distilbert",
        "supportpilot_distilbert",
    }

    # Verify CV winner is strictly linear_svm and only linear_svm
    winner_row = df[df["is_cv_winner"] == True]
    assert len(winner_row) == 1
    assert winner_row.iloc[0]["model_id"] == "linear_svm"


def test_external_score_is_descriptive_when_overlap_unknown(monkeypatch, tmp_path):
    from pipeline.evaluation.run_comparison import run_comparison

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    run_comparison(
        config_path=cfg_file,
        run_id="03-11-2026-cmp-desc",
        repo_root=tmp_path,
        output_root=out_root,
    )

    df = pd.read_csv(out_root / "03-11-2026-cmp-desc" / "comparison.csv")
    tf_rows = df[df["model_type"] == "transformer"]
    assert len(tf_rows) == 2
    for _, row in tf_rows.iterrows():
        assert row["independence_status"] == "unverified"
        assert row["eligible_for_independent_ranking"] == False


def test_local_missing_cv_is_na_not_zero(monkeypatch, tmp_path):
    from pipeline.evaluation.run_comparison import run_comparison

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    run_comparison(
        config_path=cfg_file,
        run_id="03-11-2026-cmp-cv",
        repo_root=tmp_path,
        output_root=out_root,
    )

    df = pd.read_csv(out_root / "03-11-2026-cmp-cv" / "comparison.csv")
    tf_rows = df[df["model_type"] == "transformer"]
    for _, row in tf_rows.iterrows():
        # cv_macro_f1 must be NaN, null, or empty string — never 0.0 or val score!
        assert pd.isna(row["cv_macro_f1"]) or str(row["cv_macro_f1"]).strip() == ""


def test_new_run_does_not_modify_historical_artifacts(monkeypatch, tmp_path):
    from pipeline.evaluation.run_comparison import run_comparison

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    # Snapshot historical hashes
    eval_dir = setup["eval_manifest"].parent
    hist_hashes_before = {
        p.relative_to(eval_dir).as_posix(): compute_sha256(p)
        for p in eval_dir.rglob("*")
        if p.is_file()
    }

    run_comparison(
        config_path=cfg_file,
        run_id="03-11-2026-cmp-hist",
        repo_root=tmp_path,
        output_root=out_root,
    )

    # Verify no historical file changed
    for rel_path, old_hash in hist_hashes_before.items():
        curr_p = eval_dir / rel_path
        assert curr_p.exists()
        assert compute_sha256(curr_p) == old_hash


def test_comparison_fails_if_model_fails_to_load_or_predict(monkeypatch, tmp_path):
    from pipeline.evaluation.run_comparison import run_comparison

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    # Corrupt model adapter prediction by causing predict_rows to raise an error
    def failing_predict(*args, **kwargs):
        raise RuntimeError("Inference engine crashed")

    monkeypatch.setattr("pipeline.evaluation.run_comparison.predict_rows", failing_predict)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    with pytest.raises(EvaluationError, match="Inference engine crashed"):
        run_comparison(
            config_path=cfg_file,
            run_id="03-11-2026-cmp-fail",
            repo_root=tmp_path,
            output_root=out_root,
        )

    # State file must be failed, manifest must not be created
    run_dir = out_root / "03-11-2026-cmp-fail"
    state_file = run_dir / "run_state.json"
    assert state_file.exists()
    state_data = json.loads(state_file.read_text())
    assert state_data["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()


def test_comparison_fails_if_input_file_changes_during_run(monkeypatch, tmp_path):
    from pipeline.evaluation.run_comparison import run_comparison

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    from pipeline.evaluation.evaluate_intent import predict_rows as real_predict_rows

    def tampering_predict(adapter, test_df, batch_size=256):
        # Tamper with the config file mid-run!
        cfg_file.write_text("{\"tampered\": true}")
        return real_predict_rows(adapter, test_df, batch_size=batch_size)

    monkeypatch.setattr("pipeline.evaluation.run_comparison.predict_rows", tampering_predict)

    with pytest.raises(EvaluationError, match="changed during comparison run"):
        run_comparison(
            config_path=cfg_file,
            run_id="03-11-2026-cmp-tamper",
            repo_root=tmp_path,
            output_root=out_root,
        )

    run_dir = out_root / "03-11-2026-cmp-tamper"
    state_data = json.loads((run_dir / "run_state.json").read_text())
    assert state_data["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()


# =========================================================================
# Task 5: CLI and Config Smoke Tests
# =========================================================================

def test_config_device_and_unknown_keys_rejected(tmp_path):
    from pipeline.evaluation.comparison_contracts import load_comparison_config

    setup = make_comparison_fixture(tmp_path)
    base_cfg = setup["config"]

    # Unknown key
    bad_cfg1 = dict(base_cfg)
    bad_cfg1["unexpected_key"] = "bad"
    p1 = tmp_path / "cfg1.json"
    save_json(bad_cfg1, p1)
    with pytest.raises(EvaluationError, match="unknown keys"):
        load_comparison_config(p1, repo_root=tmp_path)

    # Unsupported device
    bad_cfg2 = dict(base_cfg)
    bad_cfg2["device"] = "tpu"
    p2 = tmp_path / "cfg2.json"
    save_json(bad_cfg2, p2)
    with pytest.raises(EvaluationError, match="Unsupported device"):
        load_comparison_config(p2, repo_root=tmp_path)

    # max_length <= 0
    bad_cfg3 = dict(base_cfg)
    bad_cfg3["max_length"] = 0
    p3 = tmp_path / "cfg3.json"
    save_json(bad_cfg3, p3)
    with pytest.raises(EvaluationError, match="max_length must be a positive integer"):
        load_comparison_config(p3, repo_root=tmp_path)

    # num_threads <= 0
    bad_cfg4 = dict(base_cfg)
    bad_cfg4["num_threads"] = -1
    p4 = tmp_path / "cfg4.json"
    save_json(bad_cfg4, p4)
    with pytest.raises(EvaluationError, match="num_threads must be a positive integer"):
        load_comparison_config(p4, repo_root=tmp_path)


def test_cli_comparison_offline_smoke(monkeypatch, tmp_path, capsys):
    from pipeline.evaluation.run_comparison import main

    setup = make_comparison_fixture(tmp_path)
    _setup_mock_transformers_for_runner(monkeypatch, setup)

    cfg_file = tmp_path / "comparison_config.json"
    save_json(setup["config"], cfg_file)
    out_root = tmp_path / "artifacts" / "evaluation"

    ret = main([
        "--config", str(cfg_file),
        "--run-id", "03-11-2026-cmp-cli",
        "--repo-root", str(tmp_path),
        "--output-root", str(out_root),
    ])
    assert ret == 0

    run_dir = out_root / "03-11-2026-cmp-cli"
    cmp_csv = run_dir / "comparison.csv"
    assert cmp_csv.exists()
    df = pd.read_csv(cmp_csv)
    assert len(df) == 5

    manifest_file = run_dir / "manifest.json"
    assert manifest_file.exists()
    man = json.loads(manifest_file.read_text())
    assert man["status"] == "completed"
    assert "outputs" in man

    # Verify all output hashes match actual files on disk
    for rel_path, expected_hash in man["outputs"].items():
        actual_path = run_dir / rel_path
        assert actual_path.exists()
        assert compute_sha256(actual_path) == expected_hash


def test_cli_help_does_not_load_models():
    from pipeline.evaluation.run_comparison import main

    with pytest.raises(SystemExit) as excinfo:
        main(["--help"])
    assert excinfo.value.code == 0

