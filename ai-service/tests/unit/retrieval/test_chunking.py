"""A KB document version is cut into chunks whose snippets are passages of its body."""

import dataclasses

from app.retrieval.adapters.chunking import chunk_document
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT, KeywordEncoder

TOKEN_SPANS = KeywordEncoder().token_spans
# The minimum number of tokens of a passage, as in `main`.
MIN_PASSAGE_TOKENS = 50
LONG_BODY = " ".join(f"word{index}" for index in range(130))


def test_a_short_body_is_one_chunk_with_the_title() -> None:
    (chunk,) = chunk_document(EXAMPLE_DOCUMENT, TOKEN_SPANS, max_tokens=100, overlap_tokens=10)

    assert chunk.ordinal == 0
    assert chunk.snippet == EXAMPLE_DOCUMENT.body
    assert chunk.text == f"{EXAMPLE_DOCUMENT.title}\n{EXAMPLE_DOCUMENT.body}"
    assert chunk.token_count == len(TOKEN_SPANS(chunk.text))


def test_a_long_body_is_cut_into_overlapping_passages_of_the_body() -> None:
    document = dataclasses.replace(EXAMPLE_DOCUMENT, body=f"  {LONG_BODY}\n")

    chunks = chunk_document(document, TOKEN_SPANS, max_tokens=63, overlap_tokens=10)

    # The title takes 3 words and 2 more tokens, so each passage holds 58 words.
    assert [chunk.ordinal for chunk in chunks] == [0, 1, 2]
    assert [len(chunk.snippet.split()) for chunk in chunks] == [58, 58, 34]
    assert all(chunk.snippet in document.body for chunk in chunks)
    assert chunks[0].snippet.split()[-10:] == chunks[1].snippet.split()[:10]
    assert chunks[2].snippet.endswith("word129")


def test_a_body_of_exactly_one_passage_is_one_chunk() -> None:
    # The title takes 3 words and 2 more tokens, so a passage holds 58 words.
    document = dataclasses.replace(EXAMPLE_DOCUMENT, body=" ".join(LONG_BODY.split()[:58]))

    (chunk,) = chunk_document(document, TOKEN_SPANS, max_tokens=63, overlap_tokens=10)

    assert chunk.snippet == document.body


def test_a_passage_keeps_50_tokens_however_long_the_title() -> None:
    document = dataclasses.replace(EXAMPLE_DOCUMENT, title="t " * 80, body=LONG_BODY)

    chunks = chunk_document(document, TOKEN_SPANS, max_tokens=60, overlap_tokens=0)

    assert len(chunks[0].snippet.split()) == MIN_PASSAGE_TOKENS


def test_a_body_without_tokens_is_one_chunk() -> None:
    document = dataclasses.replace(EXAMPLE_DOCUMENT, body="   ")

    (chunk,) = chunk_document(document, TOKEN_SPANS, max_tokens=60, overlap_tokens=0)

    assert chunk.snippet == "   "
