"""Contract verification, lineage checking, and config loading for Evaluation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import pandas as pd

from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    STANDARD_INTENTS,
    compute_sha256,
    get_near_duplicate_key,
    load_json,
)
from pipeline.evaluation import EvaluationError

ALLOWED_CONFIG_KEYS = {
    "schema_version",
    "seed",
    "timing",
    "metrics",
    "expected_intents",
    "n_folds",
}
ALLOWED_TIMING_KEYS = {
    "warmup_requests",
    "benchmark_requests",
    "latency_batch_size",
    "throughput_batch_size",
}


@dataclass(frozen=True)
class VerifiedMLInputs:
    """Verified ML evaluation inputs ensuring test isolation and provenance."""

    training_manifest: dict[str, Any]
    selection: dict[str, Any]
    test: pd.DataFrame
    class_order: list[str]
    model_dirs: dict[str, Path]
    input_hashes: dict[str, str]
    source_paths: dict[str, Path]


def validate_run_id(run_id: str) -> None:
    """Validate that run ID is a single safe path component without path escape."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise EvaluationError("run_id: must be a non-empty string")
    if "/" in run_id or "\\" in run_id or ".." in run_id or " " in run_id:
        raise EvaluationError(f"run_id: {run_id!r} contains invalid path separators or spaces")
    if not re.match(r"^[\w-]+$", run_id):
        raise EvaluationError(f"run_id: {run_id!r} contains invalid characters")


def hash_inputs(paths: dict[str, Path]) -> dict[str, str]:
    """Compute SHA-256 digests for a mapping of paths."""
    digests: dict[str, str] = {}
    for name, path in paths.items():
        if not path.exists():
            raise EvaluationError(f"Cannot compute hash: file not found at {path}")
        digests[name] = compute_sha256(path)
    return digests


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and validate evaluation configuration JSON."""
    p = Path(path)
    if not p.exists():
        raise EvaluationError(f"Config file not found at {p}")
    try:
        data = load_json(p)
    except Exception as exc:
        raise EvaluationError(f"Failed to parse config JSON at {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise EvaluationError("Config root must be a JSON object")

    unknown = set(data.keys()) - ALLOWED_CONFIG_KEYS
    if unknown:
        raise EvaluationError(f"Config contains unknown keys: {sorted(unknown)}")

    if data.get("schema_version") != 1:
        raise EvaluationError("schema_version must be 1")

    timing = data.get("timing", {})
    if not isinstance(timing, dict):
        raise EvaluationError("timing must be an object")
    unknown_timing = set(timing.keys()) - ALLOWED_TIMING_KEYS
    if unknown_timing:
        raise EvaluationError(f"timing contains unknown keys: {sorted(unknown_timing)}")

    for k in ("warmup_requests", "benchmark_requests", "latency_batch_size", "throughput_batch_size"):
        if k in timing:
            val = timing[k]
            if not isinstance(val, int) or val < 0:
                raise EvaluationError(f"timing.{k} must be a non-negative integer")

    if "latency_batch_size" in timing and timing["latency_batch_size"] != 1:
        raise EvaluationError("latency_batch_size must be 1 for latency benchmark")

    return data

def _resolve_path(path_str: str, repo_root: Path) -> Path:
    p = Path(path_str)
    if p.is_absolute():
        return p
    return repo_root / p


def load_suite(path: str | Path, repo_root: str | Path, mode: str = "ml") -> dict[str, Any]:
    """Load and validate test suite manifest and case definitions."""
    p = _resolve_path(str(path), Path(repo_root))
    if not p.exists():
        raise EvaluationError(f"Suite manifest not found at {p}")
    try:
        data = load_json(p)
    except Exception as exc:
        raise EvaluationError(f"Failed to parse suite manifest JSON at {p}: {exc}") from exc

    if not isinstance(data, dict):
        raise EvaluationError("Suite manifest root must be a JSON object")

    cases = data.get("robustness_cases", [])
    if not isinstance(cases, list):
        raise EvaluationError("robustness_cases must be a list")

    seen_ids = set()
    for c in cases:
        if not isinstance(c, dict):
            raise EvaluationError("Each suite case must be a JSON object")
        cid = c.get("case_id")
        if not cid or cid in seen_ids:
            raise EvaluationError(f"Invalid or duplicate case_id: {cid}")
        seen_ids.add(cid)

    source_paths = {"suite_manifest": p}
    input_hashes = {"suite_manifest": compute_sha256(p)}
    return {
        "suite_manifest": data,
        "robustness_cases": cases,
        "source_paths": source_paths,
        "input_hashes": input_hashes,
    }


def verify_ml_inputs(
    training_manifest: str | Path,
    repo_root: str | Path,
    config: dict[str, Any],
) -> VerifiedMLInputs:
    """Verify training lineage, artifacts integrity, and extract hold-out test set."""
    root = Path(repo_root)
    t_path = _resolve_path(str(training_manifest), root)
    if not t_path.exists():
        raise EvaluationError(f"Training manifest not found at {t_path}")

    try:
        t_man = load_json(t_path)
    except Exception as exc:
        raise EvaluationError(f"Failed to parse training manifest at {t_path}: {exc}") from exc

    if not isinstance(t_man, dict):
        raise EvaluationError("Training manifest must be a JSON object")

    if t_man.get("status") != "completed":
        raise EvaluationError(f"Training run is not completed (status: {t_man.get('status')!r})")

    train_dir = t_path.parent
    t_inputs = t_man.get("inputs", {})
    t_outputs = t_man.get("outputs", {})
    prep_sec = t_man.get("preparation", {})

    prep_manifest_path_str = prep_sec.get("manifest_path")
    if not prep_manifest_path_str:
        raise EvaluationError("Training manifest missing preparation.manifest_path")
    prep_manifest_path = _resolve_path(prep_manifest_path_str, root)
    if not prep_manifest_path.exists():
        raise EvaluationError(f"Preparation manifest not found at {prep_manifest_path}")

    expected_prep_sha = prep_sec.get("manifest_sha256")
    actual_prep_sha = compute_sha256(prep_manifest_path)
    if expected_prep_sha != actual_prep_sha:
        raise EvaluationError("Preparation manifest hash mismatch")

    prep_man = load_json(prep_manifest_path)
    prep_artifacts = prep_man.get("output_artifacts", {})

    source_paths: dict[str, Path] = {
        "training_manifest": t_path,
        "preparation_manifest": prep_manifest_path,
    }

    for art_name in ("cleaned_csv", "split_assignments", "split_report"):
        art_path_str = prep_artifacts.get(art_name)
        if not art_path_str:
            raise EvaluationError(f"Preparation manifest missing {art_name}")
        art_path = _resolve_path(art_path_str, root)
        if not art_path.exists():
            raise EvaluationError(f"{art_name} not found at {art_path}")
        source_paths[art_name] = art_path
        actual_sha = compute_sha256(art_path)
        expected_sha = t_inputs.get(art_name)
        if expected_sha and actual_sha != expected_sha:
            raise EvaluationError(f"Hash mismatch for {art_name}")

    # Verify split_report hashes
    split_rep = load_json(source_paths["split_report"])
    if split_rep.get("cleaned_sha256") != compute_sha256(source_paths["cleaned_csv"]):
        raise EvaluationError("split_report.cleaned_sha256 does not match cleaned_csv")
    if split_rep.get("splits_sha256") != compute_sha256(source_paths["split_assignments"]):
        raise EvaluationError("split_report.splits_sha256 does not match split_assignments")

    # Verify models and selection
    selection = t_man.get("selection")
    if not isinstance(selection, dict):
        raise EvaluationError("Training manifest missing selection")

    sel_file = train_dir / "selection.json"
    if not sel_file.exists():
        raise EvaluationError(f"selection.json not found in training run dir: {sel_file}")
    if "selection.json" not in t_outputs:
        raise EvaluationError("Missing required checksum for selection.json in manifest outputs")
    if compute_sha256(sel_file) != t_outputs["selection.json"]:
        raise EvaluationError("Hash mismatch for selection.json")

    disk_selection = load_json(sel_file)
    if disk_selection != selection:
        raise EvaluationError("Manifest selection does not match selection.json on disk")

    target = float(selection.get("cv_target_macro_f1", 0.85))
    best_per_model = selection.get("best_per_model", {})
    if not best_per_model:
        raise EvaluationError("Selection missing best_per_model")

    winner = selection.get("winner")
    if not winner or winner.get("candidate_id") not in [m.get("candidate_id") for m in best_per_model.values()]:
        raise EvaluationError("Selection winner does not match best_per_model candidates")

    model_dirs: dict[str, Path] = {}
    for mid, binfo in best_per_model.items():
        mdir = train_dir / "models" / mid
        if not mdir.exists():
            raise EvaluationError(f"Model directory missing at {mdir}")
        model_dirs[mid] = mdir

        bpath = mdir / "bundle.joblib"
        cpath = mdir / "model_card.json"
        if not bpath.exists() or not cpath.exists():
            raise EvaluationError(f"Model artifacts missing for {mid}")

        # Mandatory verification against outputs dict
        b_rel = f"models/{mid}/bundle.joblib"
        c_rel = f"models/{mid}/model_card.json"
        if b_rel not in t_outputs:
            raise EvaluationError(f"Missing required checksum for bundle in manifest outputs: {b_rel}")
        if compute_sha256(bpath) != t_outputs[b_rel]:
            raise EvaluationError(f"Hash mismatch for {b_rel}")

        if c_rel not in t_outputs:
            raise EvaluationError(f"Missing required checksum for model card in manifest outputs: {c_rel}")
        if compute_sha256(cpath) != t_outputs[c_rel]:
            raise EvaluationError(f"Hash mismatch for {c_rel}")

        card = load_json(cpath)
        score = card.get("cv_metrics", {}).get("macro_f1_mean")
        card_target = card.get("meets_cv_target")
        expected_target = bool(score is not None and round(float(score), 6) >= target)
        if card_target != expected_target:
            raise EvaluationError(f"Model card target status mismatch for {mid}")

    # Verify datasets and extract test split
    cleaned_df = pd.read_csv(source_paths["cleaned_csv"])
    splits_df = pd.read_csv(source_paths["split_assignments"])

    if len(cleaned_df) != len(splits_df):
        raise EvaluationError(f"Count mismatch: cleaned={len(cleaned_df)}, splits={len(splits_df)}")

    cleaned_ids = set(cleaned_df["sample_id"].astype(str))
    split_ids = set(splits_df["sample_id"].astype(str))
    if cleaned_ids != split_ids:
        raise EvaluationError("sample_id set mismatch between cleaned and splits")

    if splits_df["sample_id"].duplicated().any():
        raise EvaluationError("split_assignments contains duplicate sample_id")

    merged = cleaned_df.merge(splits_df, on="sample_id", how="left", validate="one_to_one")

    partitions = set(merged["partition"].unique())
    if partitions - {"train", "test"}:
        raise EvaluationError(f"Unknown partitions: {partitions - {'train', 'test'}}")

    test_rows = merged[merged["partition"] == "test"]
    if test_rows.empty:
        raise EvaluationError("No test partition samples found")
    if (test_rows["fold"] != -1).any():
        raise EvaluationError("Test samples must have fold = -1")

    dev_rows = merged[merged["partition"] == "train"]
    n_folds = config.get("n_folds", 10)
    dev_folds = sorted(dev_rows["fold"].unique())
    if dev_folds != list(range(n_folds)):
        raise EvaluationError(f"Development folds must be 0..{n_folds - 1}, found {dev_folds}")

    # Check near-duplicate groups
    merged["_grp"] = merged["instruction"].apply(get_near_duplicate_key)
    grp_parts = merged.groupby("_grp")["partition"].nunique()
    if (grp_parts > 1).any():
        raise EvaluationError("Near-duplicate groups overlap across partitions")

    grp_folds = dev_rows.assign(_grp=dev_rows["instruction"].apply(get_near_duplicate_key)).groupby("_grp")["fold"].nunique()
    if (grp_folds > 1).any():
        raise EvaluationError("Near-duplicate groups overlap across development folds")

    grp_labels = merged.groupby("_grp")["intent"].nunique()
    if (grp_labels > 1).any():
        raise EvaluationError("Near-duplicate groups have conflicting intent labels")

    expected_classes = config.get("expected_intents")
    if expected_classes is None:
        expected_classes = sorted(STANDARD_INTENTS)
    else:
        expected_classes = sorted(expected_classes)

    cleaned_classes = set(cleaned_df["intent"].unique())
    invalid_classes = cleaned_classes - set(expected_classes)
    if invalid_classes:
        raise EvaluationError(f"Cleaned dataset contains labels outside expected taxonomy: {sorted(invalid_classes)}")
    missing_classes = set(expected_classes) - cleaned_classes
    if missing_classes:
        raise EvaluationError(f"Cleaned dataset missing expected taxonomy labels: {sorted(missing_classes)}")

    test_classes = set(test_rows["intent"].unique())
    missing_test_classes = set(expected_classes) - test_classes
    if missing_test_classes:
        raise EvaluationError(f"Test partition missing expected labels: {sorted(missing_test_classes)}")

    input_hashes = hash_inputs(source_paths)

    return VerifiedMLInputs(
        training_manifest=t_man,
        selection=selection,
        test=test_rows.copy().reset_index(drop=True),
        class_order=expected_classes,
        model_dirs=model_dirs,
        input_hashes=input_hashes,
        source_paths=source_paths,
    )

