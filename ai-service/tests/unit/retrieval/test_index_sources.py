"""The index configuration of the first release is a valid index asset (ADR-0027).

The release command copies `ai-service/index/<index_version>/index.json` into the index asset
of a release, next to the files of the encoder. The first version holds the values of `main`,
which were not tuned (ADR-0027).
"""

from pathlib import Path

import pytest

from app.release.manifest import verify_release
from app.retrieval.adapters.index_file import (
    IndexConfiguration,
    read_index_configuration,
)
from tests.unit.release.release_folder import JsonDocument, with_changes, write_release

INDEX_VERSION = "bge-small-en-v1.5-main-untuned-v1-kb-v2"
KB_VERSION = "v2"
INDEX_SOURCE = Path(__file__).parents[3] / "index" / INDEX_VERSION / "index.json"


def _name_the_first_index_version(document: JsonDocument) -> None:
    document["assets"]["index"]["version"] = INDEX_VERSION


@pytest.fixture
def index(tmp_path: Path) -> IndexConfiguration:
    assets = with_changes({"index": {"index/index.json": INDEX_SOURCE.read_bytes()}})
    manifest = write_release(tmp_path, change=_name_the_first_index_version, assets=assets)
    files = verify_release(manifest).asset_files("index")
    return read_index_configuration(files, KB_VERSION)


def test_the_index_source_holds_only_its_configuration_and_its_readme() -> None:
    assert sorted(path.name for path in INDEX_SOURCE.parent.iterdir()) == [
        "README.md",
        "index.json",
    ]


def test_the_first_index_configuration_holds_the_values_of_main_for_kb_v2(
    index: IndexConfiguration,
) -> None:
    assert index.encoder_name == "BAAI/bge-small-en-v1.5"
    assert index.query_prefix == "Represent this sentence for searching relevant passages: "
    assert (index.encoder_max_length, index.chunk_max_tokens, index.chunk_overlap_tokens) == (
        512,
        480,
        40,
    )
    assert index.relevance_min_score == pytest.approx(0.55)
