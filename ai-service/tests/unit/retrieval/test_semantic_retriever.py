"""The KB of a release is searched by the content of the message only (ADR-0005, statement 1)."""

import dataclasses
from pathlib import Path

import pytest

from app.retrieval import RetrievalError
from app.retrieval.adapters.index_file import IndexConfiguration
from app.retrieval.adapters.semantic_retriever import build_semantic_retriever
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT, FailingEncoder, KeywordEncoder

# Titles without a keyword, so only the bodies decide the similarity.
REFUND = dataclasses.replace(EXAMPLE_DOCUMENT, title="Sample", body="A refund to the card.")
EARLIER_REFUND = dataclasses.replace(REFUND, version="0.9")
DELIVERY = dataclasses.replace(
    REFUND, document_id="SAMPLE-DELIVERY-001", body="A delivery of the order."
)
CONFIGURATION = IndexConfiguration(
    encoder_name="fake/encoder",
    encoder_directory=Path("index/encoder"),
    query_prefix="",
    encoder_max_length=128,
    chunk_max_tokens=100,
    chunk_overlap_tokens=10,
    relevance_min_score=0.5,
)


def test_every_relevant_version_is_found_whatever_its_validity() -> None:
    retriever = build_semantic_retriever(
        [REFUND, EARLIER_REFUND, DELIVERY], KeywordEncoder(), CONFIGURATION, 2
    )

    matches = retriever.search("I want a refund to my card")

    assert [match.document.version for match in matches] == ["1.0", "0.9"]
    assert all(match.snippets == (REFUND.body,) for match in matches)


def test_a_message_that_matches_no_passage_finds_nothing() -> None:
    retriever = build_semantic_retriever([REFUND], KeywordEncoder(), CONFIGURATION, 2)

    assert retriever.search("Hello there") == ()


def test_a_kb_without_documents_finds_nothing_and_embeds_no_query() -> None:
    encoder = KeywordEncoder()
    retriever = build_semantic_retriever([], encoder, CONFIGURATION, 2)

    assert retriever.search("I want a refund") == ()
    assert encoder.query_count == 0


def test_a_failure_of_the_encoder_fails_the_search() -> None:
    retriever = build_semantic_retriever([REFUND], FailingEncoder(), CONFIGURATION, 2)

    with pytest.raises(RetrievalError):
        retriever.search("I want a refund")
