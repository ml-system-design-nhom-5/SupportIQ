"""The index of a release names its encoder, whose files are in a folder of their own."""

import copy
from collections.abc import Callable
from pathlib import Path

import pytest

from app.retrieval.adapters.index_file import (
    IndexConfiguration,
    read_index_configuration,
)
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import (
    INDEX_DOCUMENT,
    AssetFileChanges,
    JsonDocument,
    asset_refusal,
    json_file,
    verified_release,
)

INDEX_PATH = "index/index.json"
KB_VERSION = EXAMPLE_VERSIONS.kb_version


def test_the_index_names_its_encoder_and_how_it_indexes_the_kb(tmp_path: Path) -> None:
    configuration = read_index_configuration(
        verified_release(tmp_path).asset_files("index"), KB_VERSION
    )

    assert configuration == IndexConfiguration(
        encoder_name="fake/encoder",
        encoder_directory=tmp_path.resolve() / "index" / "encoder",
        query_prefix="A fake query prefix: ",
        encoder_max_length=128,
        chunk_max_tokens=100,
        chunk_overlap_tokens=10,
        relevance_min_score=0.5,
    )


def test_an_index_built_from_another_kb_version_is_refused(tmp_path: Path) -> None:
    files = verified_release(tmp_path).asset_files("index")

    error = asset_refusal(lambda: read_index_configuration(files, "kb-sample-2"))

    assert (error.asset, error.file_path) == ("index", INDEX_PATH)


def _index(change: Callable[[JsonDocument], None]) -> AssetFileChanges:
    document = copy.deepcopy(INDEX_DOCUMENT)
    change(document)
    return {"index": {INDEX_PATH: json_file(document)}}


# Each way to break the index asset, with the path that the refusal names.
INDEX_BREAKS: dict[str, tuple[AssetFileChanges, str | None]] = {
    "no index file": ({"index": {INDEX_PATH: None}}, None),
    "another index version": (
        _index(lambda document: document.update(version="index-sample-2")),
        INDEX_PATH,
    ),
    "another format": (
        _index(lambda document: document.update(format="supportiq-retrieval-index/interim-2")),
        INDEX_PATH,
    ),
    "an overlap as long as a chunk": (
        _index(lambda document: document["chunking"].update(overlap_tokens=100)),
        INDEX_PATH,
    ),
    "a negative overlap": (
        _index(lambda document: document["chunking"].update(overlap_tokens=-1)),
        INDEX_PATH,
    ),
    "more tokens than positions": (
        _index(lambda document: document["encoder"].update(max_length=513)),
        INDEX_PATH,
    ),
    "a score above 1": (
        _index(lambda document: document.update(relevance_min_score=1.5)),
        INDEX_PATH,
    ),
    "an encoder folder out of the release": (
        _index(lambda document: document["encoder"].update(directory="../encoder")),
        INDEX_PATH,
    ),
    "an unknown field": (_index(lambda document: document.update(extra=1)), INDEX_PATH),
    "an encoder folder without files": (
        _index(lambda document: document["encoder"].update(directory="index/other")),
        "index/other",
    ),
    "no encoder tokenizer": (
        {"index": {"index/encoder/tokenizer.json": None}},
        "index/encoder/tokenizer.json",
    ),
    "no encoder tokenizer configuration": (
        {"index": {"index/encoder/tokenizer_config.json": None}},
        "index/encoder/tokenizer_config.json",
    ),
    "no encoder weights": (
        {"index": {"index/encoder/model.safetensors": None}},
        "index/encoder/model.safetensors",
    ),
    "a file outside the encoder folder": (
        {"index": {"index/embeddings.bin": b"fake embeddings\n"}},
        "index/embeddings.bin",
    ),
    "a file of another asset in the encoder folder": (
        {"prompts": {"index/encoder/prompt.txt": b"A fake prompt.\n"}},
        "index/encoder",
    ),
}


@pytest.mark.parametrize("name", sorted(INDEX_BREAKS))
def test_an_index_that_breaks_its_format_is_refused(tmp_path: Path, name: str) -> None:
    changes, file_path = INDEX_BREAKS[name]
    files = verified_release(tmp_path, changes).asset_files("index")

    error = asset_refusal(lambda: read_index_configuration(files, KB_VERSION))

    assert (error.asset, error.file_path) == ("index", file_path)
