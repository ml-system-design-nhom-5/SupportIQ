"""A model artifact holds every part that DATA-35 requires, except calibration, or is refused."""

import copy
from collections.abc import Callable
from pathlib import Path

import pytest

from app.intent import INTENT_LABELS
from app.intent.adapters.model_artifact import read_model_artifact
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    ARTIFACT_DOCUMENT,
    MODEL_CONFIG_DOCUMENT,
    AssetFileChanges,
    JsonDocument,
    asset_refusal,
    json_file,
    verified_release,
)

ARTIFACT_PATH = "model/artifact.json"
CONFIG_PATH = "model/config.json"


def test_a_complete_artifact_is_read_with_its_labels_and_preprocessing(tmp_path: Path) -> None:
    artifact = read_model_artifact(verified_release(tmp_path).asset_files("model"))

    assert artifact.version == EXAMPLE_VERSIONS.model_version
    assert artifact.directory == tmp_path.resolve() / "model"
    assert artifact.labels == INTENT_LABELS
    assert artifact.max_length == ARTIFACT_DOCUMENT["preprocessing"]["max_length"]
    assert (
        artifact.training_data_manifest_sha256 == ARTIFACT_DOCUMENT["training_data_manifest_sha256"]
    )
    assert artifact.metrics_run_id == "train-run-sample-1"


def test_the_labels_follow_the_outputs_of_the_model(tmp_path: Path) -> None:
    config = copy.deepcopy(MODEL_CONFIG_DOCUMENT)
    config["id2label"]["0"], config["id2label"]["1"] = INTENT_LABELS[1], INTENT_LABELS[0]

    artifact = read_model_artifact(
        verified_release(tmp_path, {"model": {CONFIG_PATH: json_file(config)}}).asset_files("model")
    )

    assert artifact.labels[:2] == (INTENT_LABELS[1], INTENT_LABELS[0])


def _changed(
    path: str, base: JsonDocument, change: Callable[[JsonDocument], None]
) -> AssetFileChanges:
    document = copy.deepcopy(base)
    change(document)
    return {"model": {path: json_file(document)}}


def _artifact(change: Callable[[JsonDocument], None]) -> AssetFileChanges:
    return _changed(ARTIFACT_PATH, ARTIFACT_DOCUMENT, change)


def _config(change: Callable[[JsonDocument], None]) -> AssetFileChanges:
    return _changed(CONFIG_PATH, MODEL_CONFIG_DOCUMENT, change)


def _drop_label(document: JsonDocument) -> None:
    del document["id2label"]["45"]


def _repeat_label(document: JsonDocument) -> None:
    document["id2label"]["45"] = INTENT_LABELS[0]


def _rename_label(document: JsonDocument) -> None:
    document["id2label"]["45"] = "not_an_intent"


# Each way to break the model asset, with the path that the refusal names.
ARTIFACT_BREAKS: dict[str, tuple[AssetFileChanges, str | None]] = {
    "no artifact file": ({"model": {ARTIFACT_PATH: None}}, None),
    "another model version": (
        _artifact(lambda document: document.update(model_version="intent-model-sample-2")),
        ARTIFACT_PATH,
    ),
    "a calibration": (_artifact(lambda document: document.update(calibration={})), ARTIFACT_PATH),
    "no calibration field": (
        _artifact(lambda document: document.pop("calibration")),
        ARTIFACT_PATH,
    ),
    "no training data hash": (
        _artifact(lambda document: document.pop("training_data_manifest_sha256")),
        ARTIFACT_PATH,
    ),
    "no metrics summary": (
        _artifact(lambda document: document.pop("metrics_summary")),
        ARTIFACT_PATH,
    ),
    "no metric": (
        _artifact(lambda document: document["metrics_summary"].update(metrics={})),
        ARTIFACT_PATH,
    ),
    "no preprocessing": (_artifact(lambda document: document.pop("preprocessing")), ARTIFACT_PATH),
    "no token": (
        _artifact(lambda document: document["preprocessing"].update(max_length=0)),
        ARTIFACT_PATH,
    ),
    "more tokens than positions": (
        _artifact(lambda document: document["preprocessing"].update(max_length=513)),
        ARTIFACT_PATH,
    ),
    "no truncation": (
        _artifact(lambda document: document["preprocessing"].update(truncation=False)),
        ARTIFACT_PATH,
    ),
    "another format": (
        _artifact(lambda document: document.update(format="supportiq-model-artifact/interim-2")),
        ARTIFACT_PATH,
    ),
    "an unknown field": (_artifact(lambda document: document.update(extra=1)), ARTIFACT_PATH),
    "no weights": ({"model": {"model/model.safetensors": None}}, "model/model.safetensors"),
    "no tokenizer": ({"model": {"model/tokenizer.json": None}}, "model/tokenizer.json"),
    "no tokenizer configuration": (
        {"model": {"model/tokenizer_config.json": None}},
        "model/tokenizer_config.json",
    ),
    "no configuration": ({"model": {CONFIG_PATH: None}}, CONFIG_PATH),
    "a label missing": (_config(_drop_label), CONFIG_PATH),
    "a label twice": (_config(_repeat_label), CONFIG_PATH),
    "an unknown label": (_config(_rename_label), CONFIG_PATH),
    "another number of labels": (
        _config(lambda document: document.update(num_labels=45)),
        CONFIG_PATH,
    ),
    "no label map": (_config(lambda document: document.pop("id2label")), CONFIG_PATH),
    "a file outside the model folder": (
        {"model": {"model/extra/vocab.txt": b"fake vocabulary\n"}},
        "model/extra/vocab.txt",
    ),
    "a file of another asset in the model folder": (
        {"prompts": {"model/prompt.txt": b"A fake prompt.\n"}},
        "model",
    ),
}


@pytest.mark.parametrize("name", sorted(ARTIFACT_BREAKS))
def test_an_artifact_that_lacks_a_part_or_breaks_its_format_is_refused(
    tmp_path: Path, name: str
) -> None:
    changes, file_path = ARTIFACT_BREAKS[name]
    files = verified_release(tmp_path, changes).asset_files("model")

    error = asset_refusal(lambda: read_model_artifact(files))

    assert (error.asset, error.file_path) == ("model", file_path)
