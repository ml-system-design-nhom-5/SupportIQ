"""The encoder loads only from the index asset, embeds with CLS pooling, and keeps token spans.

These tests need torch, so they run only where the `torch` dependency group is installed
(`uv run --locked --group torch pytest -m torch`), and skip elsewhere.
"""

import dataclasses
from pathlib import Path

import numpy as np
import pytest

from supportiq_ai_service.release.manifest import ReleaseInvalidReason
from supportiq_ai_service.retrieval.adapters.bge_encoder import load_bge_encoder
from supportiq_ai_service.retrieval.adapters.in_memory_index import build_index
from supportiq_ai_service.retrieval.adapters.index_file import (
    IndexConfiguration,
    read_index_configuration,
)
from supportiq_ai_service.retrieval.adapters.semantic_retriever import SemanticRetriever
from tests.unit.release.fakes import EXAMPLE_VERSIONS
from tests.unit.release.release_folder import asset_refusal, verified_release
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT
from tests.unit.tiny_models import folder_files, write_encoder

pytestmark = pytest.mark.torch
pytest.importorskip("torch", reason="torch is installed only by the torch group, on Linux")

REFUND = dataclasses.replace(EXAMPLE_DOCUMENT, title="A fake refund", body="A refund to the card.")


@pytest.fixture
def configuration(tmp_path: Path) -> IndexConfiguration:
    encoder_folder = tmp_path / "built"
    write_encoder(encoder_folder)
    release = verified_release(
        tmp_path / "release", {"index": folder_files(encoder_folder, "index/encoder")}
    )
    return read_index_configuration(release.asset_files("index"), EXAMPLE_VERSIONS.kb_version)


def test_passages_and_queries_are_embedded_as_unit_vectors(
    configuration: IndexConfiguration,
) -> None:
    encoder = load_bge_encoder(configuration)

    passages = encoder.encode_passages(["A refund to the card.", "Where is my order?"])
    query = encoder.encode_query("my refund")

    assert passages.shape == (2, 8)
    assert query.shape == (8,)
    assert np.allclose(np.linalg.norm(passages, axis=1), 1)
    assert np.isclose(np.linalg.norm(query), 1)


def test_a_query_is_embedded_after_the_query_prefix_of_the_index(
    configuration: IndexConfiguration,
) -> None:
    encoder = load_bge_encoder(configuration)

    query = encoder.encode_query("my refund")

    assert configuration.query_prefix
    assert np.allclose(
        query, encoder.encode_passages([f"{configuration.query_prefix}my refund"])[0]
    )


def test_the_token_spans_point_into_the_text(configuration: IndexConfiguration) -> None:
    encoder = load_bge_encoder(configuration)
    text = "A refund to the card."

    spans = encoder.token_spans(text)

    assert [text[start:end] for start, end in spans] == ["A", "refund", "to", "the", "card", "."]


def test_every_snippet_of_a_search_is_a_passage_of_its_body(
    configuration: IndexConfiguration,
) -> None:
    encoder = load_bge_encoder(configuration)
    index = build_index([REFUND], encoder, max_tokens=60, overlap_tokens=0)
    # Random weights rank nothing in particular, so every passage counts as relevant here.
    retriever = SemanticRetriever(
        index, encoder, relevance_min_score=-1.0, max_chunks_per_document=2
    )

    (match,) = retriever.search("I want a refund to my card")

    assert all(snippet in REFUND.body for snippet in match.snippets)


def test_an_encoder_folder_that_lacks_a_file_fails_without_a_download(
    configuration: IndexConfiguration, tmp_path: Path
) -> None:
    incomplete = tmp_path / "incomplete"
    incomplete.mkdir()
    for name in ("config.json", "tokenizer.json", "tokenizer_config.json"):
        (incomplete / name).write_bytes((configuration.encoder_directory / name).read_bytes())

    error = asset_refusal(
        lambda: load_bge_encoder(dataclasses.replace(configuration, encoder_directory=incomplete))
    )

    # The unit tests block every socket, so a download would fail with another error.
    assert (error.reason, error.asset) == (ReleaseInvalidReason.ASSET_INVALID, "index")
