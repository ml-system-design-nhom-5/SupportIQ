"""The in-memory index ranks passages by cosine similarity and groups them by document version."""

import dataclasses
from collections.abc import Sequence

import numpy as np
import pytest

from app.retrieval import RetrievalError
from app.retrieval.adapters.in_memory_index import (
    Vectors,
    build_index,
    l2_normalized,
)
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT, KeywordEncoder

# Titles without a keyword, so only the bodies decide the similarity.
REFUND = dataclasses.replace(EXAMPLE_DOCUMENT, title="Sample", body="refund refund card")
REFUND_V2 = dataclasses.replace(REFUND, version="2.0", body="refund card card")
DELIVERY = dataclasses.replace(REFUND, document_id="SAMPLE-DELIVERY-001", body="delivery")
ENCODER = KeywordEncoder()


def test_versions_are_ranked_by_their_best_passage_and_kept_apart() -> None:
    index = build_index([DELIVERY, REFUND, REFUND_V2], ENCODER, max_tokens=60, overlap_tokens=0)

    # Similarities to "refund": 0.89, 0.45, and 0 for the delivery document.
    matches = index.search(ENCODER.encode_query("refund"), 0.4, max_chunks_per_document=2)

    assert [(match.document.version, match.document.document_id) for match in matches] == [
        ("1.0", "SAMPLE-REFUND-001"),
        ("2.0", "SAMPLE-REFUND-001"),
    ]
    assert matches[0].score > matches[1].score
    assert matches[0].snippets == ("refund refund card",)


def test_a_passage_below_the_relevance_score_is_left_out() -> None:
    index = build_index([REFUND, DELIVERY], ENCODER, max_tokens=60, overlap_tokens=0)

    matches = index.search(ENCODER.encode_query("delivery"), 0.99, max_chunks_per_document=2)

    assert [match.document.document_id for match in matches] == ["SAMPLE-DELIVERY-001"]


def test_a_passage_with_exactly_the_relevance_score_is_kept() -> None:
    index = build_index([REFUND, DELIVERY], ENCODER, max_tokens=60, overlap_tokens=0)

    # The refund document has no keyword in common with "delivery": its similarity is 0.
    matches = index.search(ENCODER.encode_query("delivery"), 0.0, max_chunks_per_document=2)

    assert [match.document.document_id for match in matches] == [
        "SAMPLE-DELIVERY-001",
        "SAMPLE-REFUND-001",
    ]
    assert matches[1].score == 0


def test_each_version_keeps_at_most_its_best_passages() -> None:
    body = " ".join(["refund"] * 55 + ["card"] * 55 + ["refund"] * 55)
    document = dataclasses.replace(REFUND, title="t", body=body)
    index = build_index([document], ENCODER, max_tokens=55, overlap_tokens=0)

    (match,) = index.search(ENCODER.encode_query("refund"), 0.0, max_chunks_per_document=2)

    assert [chunk.ordinal for chunk in index.chunks] == [0, 1, 2, 3]
    assert match.snippets == (index.chunks[0].snippet, index.chunks[3].snippet)
    assert all(snippet in body for snippet in match.snippets)


def test_an_index_of_no_document_finds_nothing() -> None:
    index = build_index([], ENCODER, max_tokens=60, overlap_tokens=0)

    assert index.search(ENCODER.encode_query("refund"), 0.0, 2) == ()


def test_a_query_of_another_dimension_is_refused() -> None:
    index = build_index([REFUND], ENCODER, max_tokens=60, overlap_tokens=0)

    with pytest.raises(RetrievalError):
        index.search(np.ones(2, dtype=np.float32), 0.0, 2)


def test_an_encoder_that_returns_another_number_of_vectors_is_refused() -> None:
    class ShortEncoder(KeywordEncoder):
        def encode_passages(self, texts: Sequence[str]) -> Vectors:
            del texts
            return np.ones((1, 4), dtype=np.float32)

    with pytest.raises(RetrievalError):
        build_index([REFUND, DELIVERY], ShortEncoder(), max_tokens=60, overlap_tokens=0)


@pytest.mark.parametrize("row", [[0.0, 0.0], [np.nan, 1.0], [np.inf, 1.0]])
def test_a_vector_without_a_direction_is_refused(row: list[float]) -> None:
    with pytest.raises(RetrievalError):
        l2_normalized(np.array([row], dtype=np.float32))


def test_vectors_are_scaled_to_length_1() -> None:
    vectors = l2_normalized(np.array([[3.0, 4.0]], dtype=np.float32))

    assert vectors.dtype == np.float32
    assert np.allclose(vectors, [[0.6, 0.8]])
