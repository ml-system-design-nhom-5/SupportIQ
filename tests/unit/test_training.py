from __future__ import annotations

import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sklearn
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.svm import LinearSVC

from pipeline.preparation.features import IntentFeaturePipeline
from pipeline.preparation.utils import compute_sha256, load_json, save_json
from pipeline.training.models import (
    CandidateSpec,
    build_estimator,
    compute_config_hash,
    expand_candidates,
    load_training_config,
    validate_training_config,
)
from pipeline.training.artifacts import (
    IntentModelBundle,
    build_model_card,
    load_bundle,
    save_bundle,
    write_json_atomic,
)
from pipeline.training.run_training import (
    load_completed_manifest,
    run_training,
    validate_run_id,
    verify_inputs,
)
from pipeline.training.cross_validate import (
    build_fold_features,
    build_oof_reports,
    refit_final_models,
    run_cross_validation,
    select_candidates,
    summarize_fold_metrics,
)
from pipeline.training import TrainingError

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "pipeline" / "configs" / "training.json"


def test_shipped_config_expands_to_nine_candidates():
    config = load_training_config(CONFIG_PATH)
    candidates = expand_candidates(config)
    assert [c.model_id for c in candidates] == (
        ["multinomial_nb"] * 3 + ["logistic_regression"] * 3 + ["linear_svm"] * 3
    )
    assert candidates[0].candidate_id == "multinomial_nb__alpha=0.1"
    assert config["n_folds"] == 10
    assert config["cv_target_macro_f1"] == 0.85
    assert config["seed"] == 42


@pytest.mark.parametrize(
    "mutate",
    [
        lambda c: c["models"].append(dict(c["models"][0])),
        lambda c: c["models"][0].update(grid={"alpha": []}),
        lambda c: c["models"][0].update(grid={"alpha": [0.0]}),
        lambda c: c["models"][0].update(model_id="random_forest"),
        lambda c: c.update(n_folds=1),
        lambda c: c["tfidf"].update(ngram_range=[2, 1]),
        lambda c: c.update(unknown_key=1),
    ],
)
def test_invalid_config_is_rejected(mutate):
    config = load_training_config(CONFIG_PATH)
    mutate(config)
    with pytest.raises(ValueError):
        validate_training_config(config)


def test_build_estimator_applies_params_and_returns_fresh_instance():
    config = load_training_config(CONFIG_PATH)
    candidates = {c.model_id: c for c in expand_candidates(config)}
    lr_a = build_estimator(candidates["logistic_regression"], config)
    lr_b = build_estimator(candidates["logistic_regression"], config)
    assert lr_a is not lr_b
    assert lr_a.get_params()["solver"] == "lbfgs"
    assert lr_a.get_params()["max_iter"] == 2000
    svm = build_estimator(candidates["linear_svm"], config)
    assert svm.get_params()["dual"] == "auto"
    assert svm.get_params()["random_state"] == 42


def test_config_hash_is_canonical_and_value_sensitive():
    assert compute_config_hash({"b": 1, "a": 2}) == compute_config_hash({"a": 2, "b": 1})
    assert compute_config_hash({"a": 2}) != compute_config_hash({"a": 3})


TEXTS = ["track my order", "cancel my order", "refund status", "where is my parcel"]
LABELS = ["track_order", "cancel_order", "refund_status", "track_order"]


def _fit_tiny_bundle(model_id="logistic_regression"):
    transformer = IntentFeaturePipeline(min_df=1, max_features=50).fit(TEXTS)
    if model_id == "linear_svm":
        classifier = LinearSVC(C=1.0, dual="auto", max_iter=5000, random_state=42)
    else:
        classifier = LogisticRegression(C=1.0, solver="lbfgs", max_iter=500)
    classifier.fit(transformer.transform(TEXTS), LABELS)
    return IntentModelBundle(
        transformer=transformer,
        classifier=classifier,
        model_id=model_id,
        candidate_id=f"{model_id}__C=1.0",
        classes_=list(classifier.classes_),
        metadata={"sklearn_version": sklearn.__version__},
    )


def test_bundle_roundtrip_and_text_normalization(tmp_path):
    bundle = _fit_tiny_bundle()
    reference = bundle.predict(["track my order"]).tolist()
    assert bundle.predict(["ＴＲＡＣＫ   ＭＹ   ＯＲＤＥＲ"]).tolist() == reference
    saved = save_bundle(bundle, tmp_path / "models" / "logistic_regression")
    loaded = load_bundle(saved.parent)
    assert loaded.predict(TEXTS).tolist() == bundle.predict(TEXTS).tolist()


def test_bundle_scores_follow_classes_order():
    bundle = _fit_tiny_bundle("linear_svm")
    scores = bundle.decision_function(TEXTS)
    predicted = bundle.predict(TEXTS).tolist()
    assert predicted == [bundle.classes_[i] for i in scores.argmax(axis=1)]


def test_svm_bundle_does_not_fake_probabilities():
    bundle = _fit_tiny_bundle("linear_svm")
    with pytest.raises(AttributeError):
        bundle.predict_proba(TEXTS)


def test_atomic_json_write_replaces_without_leftovers(tmp_path):
    target = tmp_path / "run" / "run_state.json"
    write_json_atomic({"status": "running"}, target)
    write_json_atomic({"status": "completed"}, target)
    assert load_json(target) == {"status": "completed"}
    assert [p.name for p in target.parent.iterdir()] == ["run_state.json"]


@dataclass
class PrepFixture:
    root: Path
    manifest_path: Path
    cleaned_path: Path
    splits_path: Path
    report_path: Path
    cleaned: pd.DataFrame
    assignments: pd.DataFrame


def rewrite_fixture(fx: PrepFixture) -> None:
    fx.cleaned.to_csv(fx.cleaned_path, index=False)
    fx.assignments.to_csv(fx.splits_path, index=False)
    partition = fx.assignments["partition"]
    summary = {
        "total_samples": len(fx.cleaned),
        "train_samples": int((partition == "train").sum()),
        "test_samples": int((partition == "test").sum()),
    }
    report = {
        "cleaned_sha256": compute_sha256(fx.cleaned_path),
        "splits_sha256": compute_sha256(fx.splits_path),
        "summary": summary,
    }
    save_json(report, fx.report_path)
    manifest = {
        "run_id": "prep-fixture",
        "metadata": {
            "dataset_version": "03-11-2026-02",
            "split_version": "03-11-2026-02",
            "cleaned_samples": summary["total_samples"],
            "train_samples": summary["train_samples"],
            "test_samples": summary["test_samples"],
        },
        "output_artifacts": {
            "cleaned_csv": str(fx.cleaned_path),
            "split_assignments": str(fx.splits_path),
            "split_report": str(fx.report_path),
        },
    }
    save_json(manifest, fx.manifest_path)


def make_prep_fixture(
    tmp_path,
    intents=("alpha", "beta", "gamma"),
    n_folds=2,
    samples_per_class_fold=2,
) -> PrepFixture:
    rows = []
    for intent in intents:
        for fold in range(n_folds):
            for i in range(samples_per_class_fold):
                rows.append(
                    {
                        "sample_id": f"{intent}-{fold}-{i}",
                        "instruction": f"{intent} development question {fold} {i}",
                        "intent": intent,
                        "category": "CAT",
                    }
                )
        rows.append(
            {
                "sample_id": f"{intent}-test",
                "instruction": f"{intent} heldout question",
                "intent": intent,
                "category": "CAT",
            }
        )
    cleaned = pd.DataFrame(rows)
    assignments = pd.DataFrame(
        {
            "sample_id": cleaned["sample_id"],
            "partition": np.where(cleaned["sample_id"].str.endswith("-test"), "test", "train"),
            "fold": cleaned["sample_id"].str.extract(r"-(\d+)-\d+$")[0].astype("Int64").fillna(-1).astype(int),
        }
    )
    cleaned_path = tmp_path / "cleaned.csv"
    splits_path = tmp_path / "split_assignments.csv"
    report_path = tmp_path / "split_report.json"
    manifest_path = tmp_path / "manifest.json"
    cleaned.to_csv(cleaned_path, index=False)
    assignments.to_csv(splits_path, index=False)
    fx = PrepFixture(tmp_path, manifest_path, cleaned_path, splits_path, report_path, cleaned, assignments)
    rewrite_fixture(fx)
    return fx


def test_verify_inputs_returns_development_only(tmp_path):
    fx = make_prep_fixture(tmp_path)
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    assert len(verified.development) == 12
    assert len(verified.test_sample_ids) == 3
    assert set(verified.development["sample_id"]).isdisjoint(verified.test_sample_ids)
    assert verified.class_order == ("alpha", "beta", "gamma")


def test_verify_inputs_returns_no_test_text(tmp_path):
    fx = make_prep_fixture(tmp_path)
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    test_text = set(fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"])
    assert test_text.isdisjoint(set(verified.development["instruction"]))


def test_verify_inputs_rejects_checksum_mismatch(tmp_path):
    fx = make_prep_fixture(tmp_path)
    report = load_json(fx.report_path)
    report["cleaned_sha256"] = "0" * 64
    save_json(report, fx.report_path)
    with pytest.raises(ValueError, match="cleaned_sha256"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


@pytest.mark.parametrize("break_ids", ["missing", "duplicate", "extra"])
def test_verify_inputs_rejects_bad_id_coverage(tmp_path, break_ids):
    fx = make_prep_fixture(tmp_path)
    if break_ids == "missing":
        fx.assignments = fx.assignments.iloc[:-1]
    elif break_ids == "duplicate":
        fx.assignments = pd.concat([fx.assignments, fx.assignments.iloc[[0]]])
    else:
        extra = fx.assignments.iloc[[0]].assign(sample_id="not-in-cleaned")
        fx.assignments = pd.concat([fx.assignments, extra])
    rewrite_fixture(fx)
    with pytest.raises(ValueError):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_count_mismatch(tmp_path):
    fx = make_prep_fixture(tmp_path)
    manifest = load_json(fx.manifest_path)
    manifest["metadata"]["train_samples"] += 1
    save_json(manifest, fx.manifest_path)
    with pytest.raises(ValueError, match="train_samples"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def _fold_column(fx, fold):
    fx.assignments.loc[fx.assignments["fold"] == fold, "fold"] = 99
    rewrite_fixture(fx)


def test_verify_inputs_rejects_test_fold_not_minus_one(tmp_path):
    fx = make_prep_fixture(tmp_path)
    fx.assignments.loc[fx.assignments["partition"] == "test", "fold"] = 0
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="test.*fold"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_missing_or_empty_fold(tmp_path):
    fx = make_prep_fixture(tmp_path)
    _fold_column(fx, 1)
    with pytest.raises(ValueError, match="fold"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_intent_missing_from_fold_validation(tmp_path):
    fx = make_prep_fixture(tmp_path)
    mask = (fx.cleaned["intent"] == "gamma") & fx.cleaned["sample_id"].isin(
        fx.assignments.loc[fx.assignments["fold"] == 1, "sample_id"]
    )
    fx.assignments.loc[fx.assignments["sample_id"].isin(fx.cleaned.loc[mask, "sample_id"]), "fold"] = 0
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="validation fold 1"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_near_duplicate_group_across_folds(tmp_path):
    fx = make_prep_fixture(tmp_path)
    fold0_id = fx.assignments.loc[fx.assignments["fold"] == 0, "sample_id"].iloc[0]
    fold1_id = fx.assignments.loc[fx.assignments["fold"] == 1, "sample_id"].iloc[0]
    text = fx.cleaned.loc[fx.cleaned["sample_id"] == fold0_id, "instruction"].iloc[0]
    fx.cleaned.loc[fx.cleaned["sample_id"] == fold1_id, "instruction"] = text.upper() + "!!!"
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="group"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def test_verify_inputs_rejects_conflicting_group_labels(tmp_path):
    fx = make_prep_fixture(tmp_path)
    first, second = fx.assignments["sample_id"].iloc[0], fx.assignments["sample_id"].iloc[1]
    text = fx.cleaned.loc[fx.cleaned["sample_id"] == first, "instruction"].iloc[0]
    fx.cleaned.loc[fx.cleaned["sample_id"] == second, "instruction"] = text
    fx.cleaned.loc[fx.cleaned["sample_id"] == second, "intent"] = "beta"
    rewrite_fixture(fx)
    with pytest.raises(ValueError, match="conflicting"):
        verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)


def make_cv_config(n_folds=2):
    return validate_training_config(
        {
            "schema_version": 1,
            "seed": 42,
            "n_folds": n_folds,
            "cv_target_macro_f1": 0.85,
            "tfidf": {
                "ngram_range": [1, 1],
                "max_features": 100,
                "min_df": 1,
                "sublinear_tf": True,
                "lowercase": True,
            },
            "models": [
                {
                    "model_id": "multinomial_nb",
                    "estimator": "MultinomialNB",
                    "grid": {"alpha": [0.1, 1.0]},
                    "fixed_params": {"fit_prior": True},
                },
                {
                    "model_id": "logistic_regression",
                    "estimator": "LogisticRegression",
                    "grid": {"C": [0.1, 1.0]},
                    "fixed_params": {
                        "solver": "lbfgs",
                        "max_iter": 2000,
                        "tol": 0.0001,
                        "class_weight": None,
                    },
                },
                {
                    "model_id": "linear_svm",
                    "estimator": "LinearSVC",
                    "grid": {"C": [0.1, 1.0]},
                    "fixed_params": {
                        "dual": "auto",
                        "max_iter": 5000,
                        "tol": 0.0001,
                        "class_weight": None,
                        "random_state": 42,
                    },
                },
            ],
            "tie_break": ["macro_f1_mean_desc", "macro_f1_std_asc", "config_order"],
        }
    )


def test_fold_transformer_excludes_validation_only_token():
    transformer, _, _, _ = build_fold_features(
        ["alpha common token", "beta common token"],
        ["gamma zzonlyval token"],
        {
            "ngram_range": (1, 1),
            "max_features": 100,
            "min_df": 1,
            "sublinear_tf": True,
            "lowercase": True,
        },
    )
    assert "zzonlyval" not in transformer.get_feature_names()


def test_cross_validation_runs_every_candidate_and_fold(tmp_path):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    result = run_cross_validation(
        verified.development, config, expand_candidates(config), class_order=verified.class_order
    )
    assert len(result.fold_metrics) == 6 * 2
    assert result.fold_metrics.groupby("candidate_id")["fold"].nunique().eq(2).all()
    assert (result.fold_metrics["status"] == "ok").all()
    assert (result.fold_metrics["transform_seconds"] >= 0).all()
    assert (result.fold_metrics["fit_seconds"] >= 0).all()
    assert (result.fold_metrics["predict_seconds"] >= 0).all()


def test_convergence_warning_fails_the_run(tmp_path, monkeypatch):
    def fake_fit(self, X, y):
        warnings.warn("did not converge", ConvergenceWarning)
        self.classes_ = np.array(sorted(set(y)))
        return self

    monkeypatch.setattr(LogisticRegression, "fit", fake_fit)
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    with pytest.raises(TrainingError, match="ConvergenceWarning"):
        run_cross_validation(
            verified.development, config, expand_candidates(config), class_order=verified.class_order
        )


def test_nan_metric_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "pipeline.training.cross_validate.f1_score",
        lambda *args, **kwargs: float("nan"),
    )
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    with pytest.raises(TrainingError, match="NaN"):
        run_cross_validation(
            verified.development, config, expand_candidates(config), class_order=verified.class_order
        )


def test_summary_uses_population_std_and_keeps_all_candidates():
    candidates = [
        CandidateSpec("m__C=0.1", "m", 0, {"C": 0.1}),
        CandidateSpec("m__C=1.0", "m", 1, {"C": 1.0}),
    ]
    fold_metrics = pd.DataFrame(
        [
            {
                "model_id": "m",
                "candidate_id": "m__C=0.1",
                "params": "{}",
                "fold": 0,
                "macro_f1": 0.5,
                "accuracy": 0.5,
                "weighted_f1": 0.5,
                "status": "ok",
            },
            {
                "model_id": "m",
                "candidate_id": "m__C=0.1",
                "params": "{}",
                "fold": 1,
                "macro_f1": 0.7,
                "accuracy": 0.5,
                "weighted_f1": 0.5,
                "status": "ok",
            },
        ]
    )
    summary = summarize_fold_metrics(fold_metrics, candidates, n_folds=2)
    row = summary.loc[summary["candidate_id"] == "m__C=0.1"].iloc[0]
    assert row["macro_f1_mean"] == pytest.approx(0.6)
    assert row["macro_f1_std"] == pytest.approx(0.1)
    assert len(summary) == 2
    assert not summary.loc[summary["candidate_id"] == "m__C=1.0", "eligible"].iloc[0]


def test_selection_tie_breaks_lower_std_then_config_order():
    candidates = [CandidateSpec("a", "m", 0, {}), CandidateSpec("b", "m", 1, {})]
    summary = pd.DataFrame(
        [
            {
                "candidate_id": "a",
                "model_id": "m",
                "macro_f1_mean": 0.8,
                "macro_f1_std": 0.02,
                "eligible": True,
            },
            {
                "candidate_id": "b",
                "model_id": "m",
                "macro_f1_mean": 0.8,
                "macro_f1_std": 0.01,
                "eligible": True,
            },
        ]
    )
    assert select_candidates(summary, candidates, target=0.85).winner == "b"
    summary.loc[summary["candidate_id"] == "b", "macro_f1_std"] = 0.02
    assert select_candidates(summary, candidates, target=0.85).winner == "a"


def test_oof_reports_include_false_positives_from_other_classes(tmp_path):
    oof = pd.DataFrame(
        [
            {
                "sample_id": "1",
                "fold": 0,
                "y_true": "beta",
                "y_pred": "alpha",
                "model_id": "m",
                "candidate_id": "m__C=1.0",
            },
        ]
    )
    core = build_oof_reports(
        oof,
        labels=("alpha", "beta", "gamma"),
        core_intents=("alpha",),
        report_dir=tmp_path,
    )
    assert core["m"]["per_intent"]["alpha"]["precision"] == 0.0
    assert core["m"]["macro_f1"] == 0.0
    matrix = pd.read_csv(tmp_path / "m" / "confusion_matrix.csv", index_col=0)
    assert matrix.shape == (3, 3)
    assert matrix.loc["beta", "alpha"] == 1


def test_refit_fits_one_transformer_on_all_development_rows(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    calls = []
    real_fit_transform = IntentFeaturePipeline.fit_transform

    def spy(self, texts):
        calls.append(list(texts))
        return real_fit_transform(self, texts)

    monkeypatch.setattr(IntentFeaturePipeline, "fit_transform", spy)
    candidates = expand_candidates(config)
    best = {
        m: next(c.candidate_id for c in candidates if c.model_id == m)
        for m in ("multinomial_nb", "logistic_regression", "linear_svm")
    }
    bundles = refit_final_models(verified.development, config, candidates, best)
    assert list(calls[0]) == list(verified.development["instruction"])
    assert len(bundles) == 3


def test_refit_bundle_predicts_like_classifier_and_reloads(tmp_path):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    verified = verify_inputs(fx.manifest_path, expected_intents=("alpha", "beta", "gamma"), n_folds=2)
    candidates = expand_candidates(config)
    best = {
        m: next(c.candidate_id for c in candidates if c.model_id == m)
        for m in ("multinomial_nb", "logistic_regression", "linear_svm")
    }
    bundles = refit_final_models(verified.development, config, candidates, best)
    for model_id, bundle in bundles.items():
        expected = bundle.classifier.predict(bundle.transformer.transform(TEXTS)).tolist()
        assert bundle.predict(TEXTS).tolist() == expected
        loaded = load_bundle(save_bundle(bundle, tmp_path / "models" / model_id).parent)
        assert loaded.predict(TEXTS).tolist() == expected


def test_model_card_records_scope_limits_and_release_gate():
    card = build_model_card(
        run_id="03-11-2026-training-00",
        model_id="linear_svm",
        candidate_id="linear_svm__C=1.0",
        params={"C": 1.0},
        resolved_params={"C": 1.0, "max_iter": 5000},
        cv_metrics={"macro_f1_mean": 0.8, "macro_f1_std": 0.01},
        preparation_run_id="03-11-2026-02",
        dataset_version="03-11-2026-02",
        split_version="03-11-2026-02",
        class_order=("alpha", "beta", "gamma"),
        core_intents=("alpha",),
        target_met=False,
    )
    assert card["status"] == "candidate"
    assert card["calibration"] == "not_calibrated"
    assert card["languages"] == ["en"]
    assert card["n_labels"] == 3
    assert card["evaluation_required_before_release"] is True
    assert "synthetic" in card["data_limitations"].lower()
    assert card["meets_cv_target"] is False


def _tiny_run(tmp_path, run_id="03-11-2026-training-00"):
    fx = make_prep_fixture(tmp_path)
    config = make_cv_config()
    config_path = tmp_path / "config.json"
    save_json(config, config_path)
    result = run_training(
        fx.manifest_path,
        config_path,
        run_id,
        tmp_path / "artifacts" / "training",
        expected_intents=("alpha", "beta", "gamma"),
    )
    return fx, Path(result["run_dir"])


def test_run_training_writes_complete_artifact_tree(tmp_path):
    fx, run_dir = _tiny_run(tmp_path)
    for name in (
        "config.resolved.json",
        "environment.json",
        "fold_metrics.csv",
        "candidate_summary.csv",
        "selection.json",
        "oof_predictions.csv",
        "manifest.json",
    ):
        assert (run_dir / name).exists()
    assert len(pd.read_csv(run_dir / "fold_metrics.csv")) == 6 * 2
    assert len(pd.read_csv(run_dir / "candidate_summary.csv")) == 6
    oof = pd.read_csv(run_dir / "oof_predictions.csv")
    assert oof["model_id"].nunique() == 3
    assert oof.groupby(["model_id", "sample_id"]).size().eq(1).all()
    for model_id in ("multinomial_nb", "logistic_regression", "linear_svm"):
        assert (run_dir / "models" / model_id / "bundle.joblib").exists()
        assert (run_dir / "models" / model_id / "model_card.json").exists()
        assert (run_dir / "reports" / model_id / "confusion_matrix.csv").exists()
    manifest = load_completed_manifest(run_dir)
    assert manifest["status"] == "completed"
    assert manifest["schema_version"] == 1
    for rel, digest in manifest["outputs"].items():
        assert compute_sha256(run_dir / rel) == digest


def test_run_training_refuses_existing_run_id_before_writing(tmp_path):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)
    run_dir = tmp_path / "artifacts" / "training" / "03-11-2026-training-00"
    run_dir.mkdir(parents=True)
    (run_dir / "sentinel.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_training(
            fx.manifest_path,
            config_path,
            run_dir.name,
            run_dir.parent,
            expected_intents=("alpha", "beta", "gamma"),
        )
    assert (run_dir / "sentinel.txt").read_text(encoding="utf-8") == "keep"
    assert not (run_dir / "run_state.json").exists()


def test_failed_run_leaves_failed_state_without_completed_manifest(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)

    def boom(*args, **kwargs):
        raise TrainingError("boom")

    monkeypatch.setattr("pipeline.training.run_training.run_cross_validation", boom)
    with pytest.raises(TrainingError, match="boom"):
        run_training(
            fx.manifest_path,
            config_path,
            "03-11-2026-training-01",
            tmp_path / "artifacts" / "training",
            expected_intents=("alpha", "beta", "gamma"),
        )
    run_dir = tmp_path / "artifacts" / "training" / "03-11-2026-training-01"
    assert load_json(run_dir / "run_state.json")["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()


def test_run_fails_when_input_changes_mid_run(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)
    real_cv = run_cross_validation

    def tamper_then_run(*args, **kwargs):
        fx.cleaned.loc[fx.cleaned.index[0], "instruction"] = "mutated during run"
        fx.cleaned.to_csv(fx.cleaned_path, index=False)
        return real_cv(*args, **kwargs)

    monkeypatch.setattr("pipeline.training.run_training.run_cross_validation", tamper_then_run)
    with pytest.raises(TrainingError, match="changed during run"):
        run_training(
            fx.manifest_path,
            config_path,
            "03-11-2026-training-03",
            tmp_path / "artifacts" / "training",
            expected_intents=("alpha", "beta", "gamma"),
        )
    run_dir = tmp_path / "artifacts" / "training" / "03-11-2026-training-03"
    assert load_json(run_dir / "run_state.json")["status"] == "failed"
    assert not (run_dir / "manifest.json").exists()


def test_test_changes_do_not_change_selection(tmp_path):
    fx, run_a = _tiny_run(tmp_path, "03-11-2026-training-00")
    selection_a = load_json(run_a / "selection.json")
    oof_a = pd.read_csv(run_a / "oof_predictions.csv")
    metric_cols = ["model_id", "candidate_id", "fold", "macro_f1", "accuracy", "weighted_f1"]
    metrics_a = pd.read_csv(run_a / "fold_metrics.csv")[metric_cols]
    fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"] += " modified test query"
    rewrite_fixture(fx)
    result_b = run_training(
        fx.manifest_path,
        tmp_path / "config.json",
        "03-11-2026-training-01",
        tmp_path / "artifacts" / "training",
        expected_intents=("alpha", "beta", "gamma"),
    )
    run_b = Path(result_b["run_dir"])
    selection_b = load_json(run_b / "selection.json")
    assert selection_a["winner"] == selection_b["winner"]
    assert selection_a["best_per_model"] == selection_b["best_per_model"]
    pd.testing.assert_frame_equal(oof_a, pd.read_csv(run_b / "oof_predictions.csv"))
    pd.testing.assert_frame_equal(metrics_a, pd.read_csv(run_b / "fold_metrics.csv")[metric_cols])


def test_training_never_transforms_test_text(tmp_path, monkeypatch):
    fx = make_prep_fixture(tmp_path)
    config_path = tmp_path / "config.json"
    save_json(make_cv_config(), config_path)
    seen = []
    real_transform = IntentFeaturePipeline.transform

    def spy(self, texts):
        seen.extend(list(texts))
        return real_transform(self, texts)

    monkeypatch.setattr(IntentFeaturePipeline, "transform", spy)
    run_training(
        fx.manifest_path,
        config_path,
        "03-11-2026-training-02",
        tmp_path / "artifacts" / "training",
        expected_intents=("alpha", "beta", "gamma"),
    )
    test_text = set(fx.cleaned.loc[fx.cleaned["sample_id"].str.endswith("-test"), "instruction"])
    assert test_text.isdisjoint(seen)


@pytest.mark.parametrize("bad_run_id", ["../escape", "03-11-2026-a/b", "03-11-2026-a\\b", ""])
def test_invalid_run_id_is_rejected(bad_run_id):
    with pytest.raises(ValueError):
        validate_run_id(bad_run_id)


def test_environment_and_tampered_artifact_rejected(tmp_path):
    _, run_dir = _tiny_run(tmp_path)
    environment = load_json(run_dir / "environment.json")
    assert environment["libraries"]["scikit-learn"] == sklearn.__version__
    assert environment["cpu_count"] >= 1
    assert "git_revision" in environment and "git_dirty" in environment
    (run_dir / "models" / "linear_svm" / "bundle.joblib").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum"):
        load_completed_manifest(run_dir)
