"""The command loads the two models of a release with the CPU threads of its setting.

These tests need torch, so they run only where the `torch` dependency group is installed
(`uv run --locked --group torch pytest -m torch`), and skip elsewhere.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Protocol, cast

import pytest

from supportiq_ai_service.composition_root.release_models import load_release_models
from supportiq_ai_service.intent import INTENT_LABELS
from supportiq_ai_service.intent.adapters.model_artifact import read_model_artifact
from supportiq_ai_service.retrieval.adapters.index_file import read_index_configuration
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import verified_release
from tests.unit.tiny_models import folder_files, write_classifier, write_encoder


class _Threads(Protocol):
    def get_num_threads(self) -> int: ...

    def set_num_threads(self, threads: int) -> None: ...


pytestmark = pytest.mark.torch
torch = cast(
    "_Threads",
    pytest.importorskip("torch", reason="torch is installed only by the torch group, on Linux"),
)


@pytest.fixture
def restored_threads() -> Iterator[None]:
    threads = torch.get_num_threads()
    yield
    torch.set_num_threads(threads)


@pytest.mark.usefixtures("restored_threads")
def test_both_models_load_from_the_release_with_the_threads_of_the_setting(
    tmp_path: Path,
) -> None:
    write_classifier(tmp_path / "classifier", INTENT_LABELS)
    write_encoder(tmp_path / "encoder")
    release = verified_release(
        tmp_path / "release",
        {
            "model": folder_files(tmp_path / "classifier", "model"),
            "index": folder_files(tmp_path / "encoder", "index/encoder"),
        },
    )
    artifact = read_model_artifact(release.asset_files("model"))
    index = read_index_configuration(release.asset_files("index"), EXAMPLE_VERSIONS.kb_version)

    models = load_release_models(artifact, index, 1)

    assert torch.get_num_threads() == 1
    distribution = models.classifier.classify("Where is my order?")
    assert {entry.label for entry in distribution.probabilities} == set(INTENT_LABELS)
    assert models.encoder.token_spans("Where is my order?")
