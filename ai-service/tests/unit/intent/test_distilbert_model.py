"""The DistilBERT model loads only from its checked artifact and scores every intent.

These tests need torch, so they run only where the `torch` dependency group is installed
(`uv run --locked --group torch pytest -m torch`), and skip elsewhere.
"""

import dataclasses
import math
from pathlib import Path

import pytest

from supportiq_ai_service.intent import INTENT_LABELS
from supportiq_ai_service.intent.adapters.distilbert_model import load_distilbert_classifier
from supportiq_ai_service.intent.adapters.model_artifact import ModelArtifact, read_model_artifact
from supportiq_ai_service.release.manifest import ReleaseInvalidReason
from tests.unit.release.release_folder import asset_refusal, verified_release
from tests.unit.tiny_models import folder_files, write_classifier

pytestmark = pytest.mark.torch
pytest.importorskip("torch", reason="torch is installed only by the torch group, on Linux")


@pytest.fixture
def artifact(tmp_path: Path) -> ModelArtifact:
    model_folder = tmp_path / "built"
    write_classifier(model_folder, INTENT_LABELS)
    release = verified_release(tmp_path / "release", {"model": folder_files(model_folder, "model")})
    return read_model_artifact(release.asset_files("model"))


def test_the_model_of_an_artifact_scores_every_intent(artifact: ModelArtifact) -> None:
    classifier = load_distilbert_classifier(artifact)

    distribution = classifier.classify("Where is my order? It is late.")

    assert {entry.label for entry in distribution.probabilities} == set(INTENT_LABELS)
    assert math.fsum(entry.probability for entry in distribution.probabilities) == pytest.approx(1)
    assert classifier.classify("Where is my order? It is late.") == distribution


def test_a_model_whose_label_map_differs_from_the_artifact_is_refused(
    artifact: ModelArtifact,
) -> None:
    swapped = (INTENT_LABELS[1], INTENT_LABELS[0], *INTENT_LABELS[2:])

    error = asset_refusal(
        lambda: load_distilbert_classifier(dataclasses.replace(artifact, labels=swapped))
    )

    assert error.asset == "model"


def test_a_folder_that_lacks_a_file_fails_without_a_download(
    artifact: ModelArtifact, tmp_path: Path
) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json"):
        (incomplete / name).write_bytes((artifact.directory / name).read_bytes())

    error = asset_refusal(
        lambda: load_distilbert_classifier(dataclasses.replace(artifact, directory=incomplete))
    )

    # The unit tests block every socket, so a download would fail with another error.
    assert (error.reason, error.asset) == (ReleaseInvalidReason.ASSET_INVALID, "model")
