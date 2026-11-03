"""Training run orchestration, input verification, and manifest generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Collection

import pandas as pd

from pipeline.preparation.utils import (
    STANDARD_INTENTS,
    compute_sha256,
    get_near_duplicate_key,
    load_json,
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
    _check(isinstance(path_value, str) and bool(path_value.strip()), "path", f"invalid path {path_value!r}")
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
