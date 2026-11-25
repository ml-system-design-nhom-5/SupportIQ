"""The index configurations of `ai-service/index/` are valid index assets (ADR-0027).

The release command copies `ai-service/index/<index_version>/index.json` into the index asset
of a release, next to the files of the encoder. Each version holds the values of `main`, which
were not tuned (ADR-0027), and differs from the others only in the KB version that it indexes.
"""

from pathlib import Path

import pytest

from app.release.manifest import verify_release
from app.retrieval.adapters.index_file import (
    IndexConfiguration,
    read_index_configuration,
)
from tests.unit.release.release_folder import JsonDocument, with_changes, write_release

INDEX_SOURCES = Path(__file__).parents[3] / "index"
KB_VERSION_OF_INDEX = {
    "bge-small-en-v1.5-main-untuned-v1-kb-v2": "v2",
    "bge-small-en-v1.5-main-untuned-v1-kb-v2.1": "v2.1",
}
INDEX_VERSIONS = sorted(KB_VERSION_OF_INDEX)


@pytest.fixture
def index(tmp_path: Path, index_version: str) -> IndexConfiguration:
    def name_the_index_version(document: JsonDocument) -> None:
        document["assets"]["index"]["version"] = index_version

    source = INDEX_SOURCES / index_version / "index.json"
    assets = with_changes({"index": {"index/index.json": source.read_bytes()}})
    manifest = write_release(tmp_path, change=name_the_index_version, assets=assets)
    files = verify_release(manifest).asset_files("index")
    return read_index_configuration(files, KB_VERSION_OF_INDEX[index_version])


def test_the_index_sources_are_exactly_the_versions_that_these_tests_check() -> None:
    assert sorted(path.name for path in INDEX_SOURCES.iterdir()) == INDEX_VERSIONS


@pytest.mark.parametrize("index_version", INDEX_VERSIONS)
def test_the_index_source_holds_only_its_configuration_and_its_readme(index_version: str) -> None:
    assert sorted(path.name for path in (INDEX_SOURCES / index_version).iterdir()) == [
        "README.md",
        "index.json",
    ]


@pytest.mark.parametrize("index_version", INDEX_VERSIONS)
def test_each_index_configuration_holds_the_values_of_main_for_its_kb_version(
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
