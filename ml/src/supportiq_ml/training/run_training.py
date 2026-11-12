"""Training run orchestration, input verification, and manifest generation."""

from __future__ import annotations

import argparse
import datetime
import importlib.metadata
import os
import platform
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection

import pandas as pd

from pipeline.preparation.utils import (
    CORE_PRODUCT_INTENTS,
    STANDARD_INTENTS,
    compute_sha256,
    get_near_duplicate_key,
    get_next_id,
    load_json,
)
from pipeline.training import TrainingError
from pipeline.training.artifacts import (
    build_model_card,
    load_bundle,
    save_bundle,
    write_csv_atomic,
    write_json_atomic,
)
from pipeline.training.cross_validate import (
    build_oof_reports,
    refit_final_models,
    run_cross_validation,
    select_candidates,
    summarize_fold_metrics,
)
from pipeline.training.models import (
    compute_config_hash,
    expand_candidates,
    load_training_config,
    validate_training_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class VerifiedInputs:
    """Training inputs after all data-contract checks have passed."""

    development: pd.DataFrame
    test_sample_ids: tuple[str, ...]
    class_order: tuple[str, ...]
    manifest: dict[str, Any]
    split_report: dict[str, Any]
    paths: dict[str, Path]
    checksums: dict[str, str]


def _check(condition: bool, field: str, message: str) -> None:
    if not condition:
        raise ValueError(f"{field}: {message}")


def _resolve(path_value: Any, repo_root: Path) -> Path:
    _check(
        isinstance(path_value, (str, Path)) and bool(str(path_value).strip()),
        "path",
        f"invalid path {path_value!r}",
    )
    path = Path(path_value)
    return path if path.is_absolute() else (repo_root / path)


def _is_blank(series: pd.Series) -> pd.Series:
    return series.isna() | (series.astype(str).str.strip() == "")


def verify_inputs(
    preparation_manifest: str | Path,
    *,
    expected_intents: Collection[str] = STANDARD_INTENTS,
    n_folds: int = 10,
    repo_root: Path = REPO_ROOT,
) -> VerifiedInputs:
    """Validate Preparation artifacts before any model training work starts."""
    manifest_path = _resolve(str(preparation_manifest), repo_root)
    _check(manifest_path.exists(), "preparation_manifest", f"not found at {manifest_path}")
    manifest = load_json(manifest_path)
    _check(isinstance(manifest, dict), "manifest", "expected a JSON object")
    _check(isinstance(manifest.get("run_id"), str) and bool(manifest["run_id"]), "run_id", "missing")

    metadata = manifest.get("metadata")
    _check(isinstance(metadata, dict), "metadata", "missing or invalid")
    for key in ("dataset_version", "split_version"):
        _check(
            isinstance(metadata.get(key), str) and bool(metadata[key]),
            f"metadata.{key}",
            "missing",
        )

    artifacts = manifest.get("output_artifacts")
    _check(isinstance(artifacts, dict), "output_artifacts", "missing or invalid")
    paths: dict[str, Path] = {}
    for name in ("cleaned_csv", "split_assignments", "split_report"):
        _check(name in artifacts, f"output_artifacts.{name}", "missing")
        paths[name] = _resolve(artifacts[name], repo_root)
        _check(paths[name].exists(), f"output_artifacts.{name}", f"not found at {paths[name]}")
    paths["preparation_manifest"] = manifest_path

    cleaned = pd.read_csv(paths["cleaned_csv"])
    _check(not cleaned.empty, "cleaned_csv", "is empty")
    for column in ("sample_id", "instruction", "intent", "category"):
        _check(column in cleaned.columns, "cleaned_csv", f"missing column {column!r}")
        _check(not _is_blank(cleaned[column]).any(), column, "contains null or blank values")
    _check(not cleaned["sample_id"].duplicated().any(), "sample_id", "contains duplicate ids")

    expected = set(expected_intents)
    actual_intents = set(cleaned["intent"].astype(str))
    invalid_intents = actual_intents - expected
    _check(not invalid_intents, "intent", f"contains labels outside taxonomy: {sorted(invalid_intents)}")
    missing_intents = expected - actual_intents
    _check(not missing_intents, "intent", f"missing labels: {sorted(missing_intents)}")

    assignments = pd.read_csv(paths["split_assignments"])
    for column in ("sample_id", "partition", "fold"):
        _check(column in assignments.columns, "split_assignments", f"missing column {column!r}")
    _check(not _is_blank(assignments["sample_id"]).any(), "split_assignments.sample_id", "contains null or blank values")
    _check(
        not assignments["sample_id"].duplicated().any(),
        "split_assignments.sample_id",
        "contains duplicate ids",
    )
    cleaned_ids = set(cleaned["sample_id"].astype(str))
    assignment_ids = set(assignments["sample_id"].astype(str))
    _check(
        assignment_ids == cleaned_ids,
        "split_assignments.sample_id",
        f"coverage mismatch: missing {len(cleaned_ids - assignment_ids)}, "
        f"extra {len(assignment_ids - cleaned_ids)}",
    )

    merged = cleaned.merge(assignments, on="sample_id", how="left", validate="one_to_one")
    _check(not merged["partition"].isna().any(), "split_assignments", "join produced unassigned samples")

    split_report = load_json(paths["split_report"])
    _check(isinstance(split_report, dict), "split_report", "expected a JSON object")
    checksums = {
        "cleaned_csv": compute_sha256(paths["cleaned_csv"]),
        "split_assignments": compute_sha256(paths["split_assignments"]),
        "split_report": compute_sha256(paths["split_report"]),
    }
    _check(
        checksums["cleaned_csv"] == str(split_report.get("cleaned_sha256", "")).upper(),
        "cleaned_sha256",
        "checksum mismatch between split_report and cleaned.csv",
    )
    _check(
        checksums["split_assignments"] == str(split_report.get("splits_sha256", "")).upper(),
        "splits_sha256",
        "checksum mismatch between split_report and split_assignments.csv",
    )

    summary = split_report.get("summary")
    _check(isinstance(summary, dict), "split_report.summary", "missing or invalid")
    train_count = int((merged["partition"] == "train").sum())
    test_count = int((merged["partition"] == "test").sum())
    expected_counts = {
        "total_samples": len(cleaned),
        "train_samples": train_count,
        "test_samples": test_count,
    }
    for key, actual in expected_counts.items():
        _check(
            summary.get(key) == actual,
            f"split_report.summary.{key}",
            f"expected {actual}, found {summary.get(key)!r}",
        )
    metadata_counts = {
        "cleaned_samples": len(cleaned),
        "train_samples": train_count,
        "test_samples": test_count,
    }
    for key, actual in metadata_counts.items():
        _check(
            metadata.get(key) == actual,
            key,
            f"expected {actual}, found {metadata.get(key)!r}",
        )

    partitions = set(merged["partition"].astype(str))
    _check(partitions <= {"train", "test"}, "partition", f"unexpected partitions {sorted(partitions - {'train', 'test'})}")
    _check({"train", "test"} <= partitions, "partition", "both train and test partitions are required")

    test_folds = set(merged.loc[merged["partition"] == "test", "fold"].tolist())
    _check(test_folds == {-1}, "test fold", f"test partition must have fold -1, found {sorted(test_folds)}")

    development_rows = merged[merged["partition"] == "train"]
    development_folds = sorted(set(development_rows["fold"].tolist()))
    _check(
        development_folds == list(range(n_folds)),
        "fold",
        f"development folds must be exactly 0..{n_folds - 1}, found {development_folds}",
    )
    fold_sizes = development_rows.groupby("fold").size()
    _check((fold_sizes > 0).all(), "fold", "development contains an empty fold")

    merged["group_key"] = merged["instruction"].apply(get_near_duplicate_key)
    group_shape = merged.groupby("group_key").agg(
        partitions=("partition", "nunique"),
        folds=("fold", "nunique"),
    )
    spanning = group_shape[(group_shape["partitions"] > 1) | (group_shape["folds"] > 1)]
    _check(
        spanning.empty,
        "group",
        f"{len(spanning)} near-duplicate group(s) span multiple partitions or folds",
    )
    group_labels = merged.groupby("group_key")["intent"].nunique()
    conflicting = group_labels[group_labels > 1]
    _check(
        conflicting.empty,
        "conflicting group labels",
        f"{len(conflicting)} near-duplicate group(s) carry different intents",
    )

    test_intents = set(merged.loc[merged["partition"] == "test", "intent"].astype(str))
    missing_test = expected - test_intents
    _check(not missing_test, "intent", f"missing from test: {sorted(missing_test)}")
    for fold in range(n_folds):
        validation_intents = set(development_rows.loc[development_rows["fold"] == fold, "intent"].astype(str))
        missing_validation = expected - validation_intents
        _check(
            not missing_validation,
            "intent",
            f"intent {sorted(missing_validation)!r} missing from validation fold {fold}",
        )
    for fold in range(n_folds):
        train_intents = set(development_rows.loc[development_rows["fold"] != fold, "intent"].astype(str))
        missing_train = expected - train_intents
        _check(not missing_train, "intent", f"missing from training fold {fold}: {sorted(missing_train)}")

    development = merged.loc[merged["partition"] == "train", list(cleaned.columns) + ["fold", "group_key"]].copy()
    development = development.reset_index(drop=True)
    test_sample_ids = tuple(merged.loc[merged["partition"] == "test", "sample_id"].astype(str))
    class_order = tuple(sorted(expected))

    return VerifiedInputs(
        development=development,
        test_sample_ids=test_sample_ids,
        class_order=class_order,
        manifest=manifest,
        split_report=split_report,
        paths=paths,
        checksums=checksums,
    )


def validate_run_id(run_id: str) -> str:
    """Validate that run ID strictly matches DD-MM-YYYY-stt format."""
    if not isinstance(run_id, str):
        raise ValueError("run_id: must be a string")
    pattern = re.compile(r"^\d{2}-\d{2}-\d{4}-\d{2,}$")
    if not pattern.match(run_id) or "/" in run_id or "\\" in run_id or ".." in run_id:
        raise ValueError(
            f"run_id: {run_id!r} is invalid; expected format DD-MM-YYYY-stt (e.g. '03-11-2026-00')"
        )
    return run_id


def capture_environment(repo_root: Path) -> dict[str, Any]:
    """Capture library versions, hardware, OS, and Git lineage."""
    lib_names = ["pandas", "numpy", "scikit-learn", "scipy", "joblib"]
    libraries: dict[str, str] = {}
    for name in lib_names:
        try:
            libraries[name] = importlib.metadata.version(name)
        except Exception:
            libraries[name] = "unknown"

    git_revision: str | None = None
    git_dirty: bool | None = None
    try:
        rev = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if rev.returncode == 0:
            git_revision = rev.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if status.returncode == 0:
            git_dirty = bool(status.stdout.strip())
    except Exception:
        pass

    return {
        "python_version": sys.version,
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count() or 1,
        "libraries": libraries,
        "git_revision": git_revision,
        "git_dirty": git_dirty,
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def load_completed_manifest(run_dir: Path | str) -> dict[str, Any]:
    """Load a manifest from completed run directory and verify all output digests."""
    base = Path(run_dir)
    manifest_path = base / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found at {manifest_path}")
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("status") != "completed":
        raise ValueError(f"Run is not completed: status is {manifest.get('status')!r}")

    outputs = manifest.get("outputs", {})
    if not isinstance(outputs, dict):
        raise ValueError("manifest.outputs: missing or invalid")

    for rel, expected_digest in outputs.items():
        file_path = base / rel
        if not file_path.exists():
            raise ValueError(f"Output file missing: {rel}")
        actual_digest = compute_sha256(file_path)
        if actual_digest != expected_digest:
            raise ValueError(f"checksum mismatch: {rel}")

    return manifest


def run_training(
    preparation_manifest: str | Path,
    config_path: str | Path,
    run_id: str | None = None,
    output_root: str | Path = "artifacts/training",
    *,
    expected_intents: Collection[str] = STANDARD_INTENTS,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Execute end-to-end training, CV selection, refitting, and artifact emission."""
    root = Path(repo_root)
    out_base = _resolve(output_root, root)
    if run_id is None:
        run_id = get_next_id(out_base)
    else:
        run_id = validate_run_id(run_id)

    run_dir = out_base / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists at {run_dir}")

    resolved_cfg_path = _resolve(config_path, root)
    raw_config = load_training_config(resolved_cfg_path)
    config = validate_training_config(raw_config)
    config_hash = compute_config_hash(config)

    run_dir.mkdir(parents=True, exist_ok=False)
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state_file = run_dir / "run_state.json"
    write_json_atomic({"status": "running", "started_at": created_at}, state_file)

    try:
        verified = verify_inputs(
            preparation_manifest,
            expected_intents=expected_intents,
            n_folds=config["n_folds"],
            repo_root=root,
        )
        initial_inputs = {
            "preparation_manifest": compute_sha256(verified.paths["preparation_manifest"]),
            "cleaned_csv": verified.checksums["cleaned_csv"],
            "split_assignments": verified.checksums["split_assignments"],
            "split_report": verified.checksums["split_report"],
            "config": compute_sha256(resolved_cfg_path),
        }

        candidates = expand_candidates(config)
        write_json_atomic(
            {
                "config": config,
                "config_hash": config_hash,
                "candidates": [
                    {
                        "candidate_id": c.candidate_id,
                        "model_id": c.model_id,
                        "order": c.order,
                        "params": c.params,
                    }
                    for c in candidates
                ],
            },
            run_dir / "config.resolved.json",
        )
        env = capture_environment(root)
        write_json_atomic(env, run_dir / "environment.json")

        def _on_fold(df: pd.DataFrame) -> None:
            write_csv_atomic(df, run_dir / "fold_metrics.csv", index=False)
            completed_folds = df["fold"].nunique()
            print(f"  -> Fold {completed_folds}/{config['n_folds']} done ({len(df)} fits recorded)")

        cv_res = run_cross_validation(
            verified.development,
            config,
            candidates,
            class_order=verified.class_order,
            on_fold=_on_fold,
        )

        summary = summarize_fold_metrics(
            cv_res.fold_metrics, candidates, n_folds=config["n_folds"]
        )
        write_csv_atomic(summary, run_dir / "candidate_summary.csv", index=False)

        selection = select_candidates(summary, candidates, target=config["cv_target_macro_f1"])
        write_json_atomic(selection.payload, run_dir / "selection.json")

        best_cand_ids = set(selection.best_per_model.values())
        oof_best = cv_res.oof_predictions[cv_res.oof_predictions["candidate_id"].isin(best_cand_ids)].copy()
        write_csv_atomic(oof_best, run_dir / "oof_predictions.csv", index=False)

        build_oof_reports(
            oof_best,
            labels=verified.class_order,
            core_intents=CORE_PRODUCT_INTENTS,
            report_dir=run_dir / "reports",
        )

        bundles = refit_final_models(
            verified.development,
            config,
            candidates,
            selection.best_per_model,
            metadata={
                "training_run_id": run_id,
                "preparation_run_id": verified.manifest["run_id"],
                "dataset_version": verified.manifest["metadata"]["dataset_version"],
                "split_version": verified.manifest["metadata"]["split_version"],
                "class_order": list(verified.class_order),
            },
        )

        for model_id, bundle in bundles.items():
            model_dir = run_dir / "models" / model_id
            save_bundle(bundle, model_dir)
            best_info = selection.payload["best_per_model"][model_id]
            model_macro_mean = best_info.get("macro_f1_mean")
            model_target_met = bool(
                model_macro_mean is not None
                and round(float(model_macro_mean), 6) >= float(config["cv_target_macro_f1"])
            )
            card = build_model_card(
                run_id=run_id,
                model_id=model_id,
                candidate_id=bundle.candidate_id,
                params=best_info["params"],
                resolved_params=bundle.metadata.get("resolved_params", {}),
                cv_metrics={k: v for k, v in best_info.items() if "mean" in k or "std" in k},
                preparation_run_id=verified.manifest["run_id"],
                dataset_version=verified.manifest["metadata"]["dataset_version"],
                split_version=verified.manifest["metadata"]["split_version"],
                class_order=verified.class_order,
                core_intents=CORE_PRODUCT_INTENTS,
                target_met=model_target_met,
            )
            write_json_atomic(card, model_dir / "model_card.json")
            loaded_b = load_bundle(model_dir)
            loaded_b.predict([str(verified.development["instruction"].iloc[0])])

        # Verify inputs did not change mid-run
        current_inputs = {
            "preparation_manifest": compute_sha256(verified.paths["preparation_manifest"]),
            "cleaned_csv": compute_sha256(verified.paths["cleaned_csv"]),
            "split_assignments": compute_sha256(verified.paths["split_assignments"]),
            "split_report": compute_sha256(verified.paths["split_report"]),
            "config": compute_sha256(resolved_cfg_path),
        }
        for key, initial_hash in initial_inputs.items():
            if current_inputs[key] != initial_hash:
                raise TrainingError(f"input {key} changed during run")

        completed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json_atomic({"status": "completed", "completed_at": completed_at}, state_file)

        # Hash all outputs excluding manifest.json
        outputs: dict[str, str] = {}
        for file_path in sorted(run_dir.rglob("*")):
            if file_path.is_file() and file_path.name != "manifest.json":
                rel = file_path.relative_to(run_dir).as_posix()
                outputs[rel] = compute_sha256(file_path)

        manifest_data = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "completed",
            "created_at": created_at,
            "completed_at": completed_at,
            "preparation": {
                "run_id": verified.manifest["run_id"],
                "dataset_version": verified.manifest["metadata"]["dataset_version"],
                "split_version": verified.manifest["metadata"]["split_version"],
                "manifest_path": str(verified.paths["preparation_manifest"]),
                "manifest_sha256": initial_inputs["preparation_manifest"],
            },
            "seed": config["seed"],
            "config_hash": config_hash,
            "inputs": initial_inputs,
            "outputs": outputs,
            "environment": env,
            "selection": selection.payload,
        }
        manifest_file = run_dir / "manifest.json"
        write_json_atomic(manifest_data, manifest_file)

        return {
            "run_id": run_id,
            "run_dir": str(run_dir),
            "manifest_path": str(manifest_file),
            "selection": selection.payload,
        }
    except Exception as exc:
        write_json_atomic(
            {"status": "failed", "error": {"type": type(exc).__name__, "message": str(exc)}},
            state_file,
        )
        raise


def main(argv: Sequence[str] | None = None) -> None:
    """CLI entrypoint for running the training pipeline."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Run Training pipeline for SupportIQ intent models.")
    parser.add_argument("--preparation-manifest", required=True, help="Path to preparation manifest.json")
    parser.add_argument("--config", required=True, help="Path to training.json")
    parser.add_argument("--run-id", default=None, help="Run ID in DD-MM-YYYY-stt format. If None, auto-generated.")
    parser.add_argument("--output-root", default="artifacts/training", help="Root dir for training runs")
    args = parser.parse_args(argv)

    try:
        result = run_training(
            preparation_manifest=args.preparation_manifest,
            config_path=args.config,
            run_id=args.run_id,
            output_root=args.output_root,
        )
        print(f"=== Training completed successfully! Run dir: {result['run_dir']} ===")
        print(f"Winner: {result['selection']['winner']['candidate_id']}")
    except Exception as exc:
        print(f"Training failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
