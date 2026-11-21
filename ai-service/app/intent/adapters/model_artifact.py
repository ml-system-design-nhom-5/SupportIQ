"""The interim format of the model artifact, and its check before the model is loaded.

The model asset of a release is one folder: the files of the model library (weights,
`config.json` with the label map, and the tokenizer files) and `artifact.json`, which states
what DATA-35 requires and the model library does not hold. `ai-service` refuses an artifact
that lacks any of these (ERR-17), except calibration: the first release has none, so the
model's scores are not calibrated (README.md, Known limits). A data contract in `contracts/`
replaces this format (ADR-0021, Follow-ups).

`artifact.json` holds:

- `model_version`: the version of the artifact, equal to the version of the asset in the
  release manifest;
- `preprocessing`: how a message is tokenized, which serving applies exactly;
- `training_data_manifest_sha256`: the SHA-256 of the manifest of the training data;
- `metrics_summary`: the run of `ml/runs/` that measured the artifact, and its metrics;
- `calibration`: always `null` in this format.
"""

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.intent.domain import INTENT_LABELS
from app.release.assets import (
    AssetFile,
    AssetFiles,
    AssetVersionText,
    Sha256,
    StrictDocument,
    read_json_asset,
)

MODEL_ARTIFACT_FORMAT = "supportiq-model-artifact/interim-1"
ARTIFACT_FILE_NAME = "artifact.json"
# The files that the model library reads from the folder of the model. `tokenizer_config.json`
# fixes the tokenizer class and its options, which the library would otherwise guess, so
# serving tokenizes as training did (DATA-35). Each is checked against the manifest.
_CONFIG_FILE_NAME = "config.json"
MODEL_LIBRARY_FILE_NAMES = (
    _CONFIG_FILE_NAME,
    "model.safetensors",
    "tokenizer.json",
    "tokenizer_config.json",
)
# DistilBERT holds 512 positions, so no tokenization can be longer.
_MAX_POSITIONS = 512
_RUN_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$"
_METRIC_NAME_PATTERN = r"^[a-z][a-z0-9_]{0,63}$"

MetricName = Annotated[str, StringConstraints(pattern=_METRIC_NAME_PATTERN)]
FiniteNumber = Annotated[float, Field(allow_inf_nan=False)]


class _Preprocessing(StrictDocument):
    max_length: Annotated[int, Field(ge=1, le=_MAX_POSITIONS)]
    padding: Literal["max_length"]
    truncation: Literal[True]


class _MetricsSummary(StrictDocument):
    run_id: Annotated[str, StringConstraints(pattern=_RUN_ID_PATTERN)]
    metrics: Annotated[dict[MetricName, FiniteNumber], Field(min_length=1)]


class _ArtifactDocument(StrictDocument):
    format: Literal["supportiq-model-artifact/interim-1"]
    model_version: AssetVersionText
    preprocessing: _Preprocessing
    training_data_manifest_sha256: Sha256
    metrics_summary: _MetricsSummary
    calibration: None


class _ModelConfig(BaseModel):
    # The configuration file of the model library: only the label map is read here, so every
    # other field of the library is left as it is.
    model_config = ConfigDict(extra="ignore", frozen=True, strict=True)

    id2label: dict[str, str]
    num_labels: int | None = None


@dataclass(frozen=True, slots=True)
class ModelArtifact:
    """A model artifact that holds every part DATA-35 requires, except calibration.

    Attributes:
        version: The version of the artifact, as the release manifest names it.
        directory: The folder of the model, which holds only the files of the artifact.
        labels: The intent label of each output of the model, by its index.
        max_length: The number of tokens of every tokenized message.
        training_data_manifest_sha256: The SHA-256 of the manifest of the training data.
        metrics_run_id: The run of `ml/runs/` that measured the artifact.
    """

    version: str
    directory: Path
    labels: tuple[str, ...]
    max_length: int
    training_data_manifest_sha256: str
    metrics_run_id: str


def read_model_artifact(files: AssetFiles) -> ModelArtifact:
    """Check the model asset of a verified release, without loading the model.

    Args:
        files: The files of the model asset.

    Returns:
        The artifact.

    Raises:
        ReleaseInvalidError: The artifact lacks a part, breaks its format, names another
            version, or holds a label map that is not one output for each of the 46 intents.
    """
    artifact_file = files.named(ARTIFACT_FILE_NAME)
    directory_path = PurePosixPath(artifact_file.file_path).parent.as_posix()
    directory = files.directory(directory_path)
    for asset_file in files.files:
        # The model library reads one folder, so a file elsewhere would never be served.
        if PurePosixPath(asset_file.file_path).parent.as_posix() != directory_path:
            raise asset_file.invalid()
    document = read_json_asset(artifact_file, _ArtifactDocument)
    if document.model_version != files.version:
        raise artifact_file.invalid()
    for name in MODEL_LIBRARY_FILE_NAMES:
        files.file(f"{directory_path}/{name}")
    return ModelArtifact(
        version=document.model_version,
        directory=directory,
        labels=_labels_by_output(files.file(f"{directory_path}/{_CONFIG_FILE_NAME}")),
        max_length=document.preprocessing.max_length,
        training_data_manifest_sha256=document.training_data_manifest_sha256,
        metrics_run_id=document.metrics_summary.run_id,
    )


def _labels_by_output(config_file: AssetFile) -> tuple[str, ...]:
    # The label map names each of the 46 intents once, for the outputs 0 to 45.
    config = read_json_asset(config_file, _ModelConfig)
    label_count = len(INTENT_LABELS)
    outputs = [str(output) for output in range(label_count)]
    if config.num_labels not in {None, label_count} or set(config.id2label) != set(outputs):
        raise config_file.invalid()
    labels = tuple(config.id2label[output] for output in outputs)
    if set(labels) != set(INTENT_LABELS):
        raise config_file.invalid()
    return labels
