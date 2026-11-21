"""The token spans of the BGE tokenizer point into the original text, so snippets stay passages.

The tokenizer lowercases, as BERT tokenizers do, yet each span points at the characters of the
original text. A chunk built from these spans is therefore a passage of the body, unlike the
decoded tokens that `main` kept. The tokenizer needs no torch, so this test runs everywhere.
"""

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from typing import NoReturn, Protocol, cast

from transformers import AutoTokenizer

from app.retrieval.adapters.bge_encoder import BgeEncoder
from app.retrieval.adapters.chunking import chunk_document
from app.retrieval.adapters.index_file import IndexConfiguration
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT
from tests.unit.tiny_models import write_tokenizer


class _Loader(Protocol):
    def from_pretrained(self, directory: Path, *, local_files_only: bool) -> object: ...


class _Tokenizer(Protocol):
    is_fast: bool

    def __call__(self, text: str | list[str], **options: object) -> Mapping[str, object]: ...


class _NoModel:
    """A stand-in for the encoder model, which computing token spans never calls."""

    def __call__(self, **inputs: object) -> NoReturn:
        """Fail, because token spans never run the model.

        Raises:
            AssertionError: Always.
        """
        raise AssertionError(inputs)

    def eval(self) -> object:
        """Return itself."""
        return self

    def requires_grad_(self, requires_grad: bool) -> object:
        """Return itself."""
        del requires_grad
        return self


def _encoder(folder: Path) -> BgeEncoder:
    write_tokenizer(folder)
    tokenizer = cast(
        "_Tokenizer", cast("_Loader", AutoTokenizer).from_pretrained(folder, local_files_only=True)
    )
    configuration = IndexConfiguration(
        encoder_name="fake/encoder",
        encoder_directory=folder,
        query_prefix="",
        encoder_max_length=128,
        chunk_max_tokens=60,
        chunk_overlap_tokens=10,
        relevance_min_score=0.5,
    )
    return BgeEncoder(configuration, tokenizer, _NoModel())


def test_each_span_points_at_the_characters_of_the_original_text(tmp_path: Path) -> None:
    text = "A REFUND to the Card."

    spans = _encoder(tmp_path).token_spans(text)

    assert [text[start:end] for start, end in spans] == ["A", "REFUND", "to", "the", "Card", "."]


def test_chunks_built_from_the_spans_are_passages_of_the_body(tmp_path: Path) -> None:
    body = "A   REFUND to the Card.\n" * 40
    document = dataclasses.replace(EXAMPLE_DOCUMENT, body=body)

    chunks = chunk_document(document, _encoder(tmp_path).token_spans, 60, 10)

    assert len(chunks) > 1
    assert all(chunk.snippet in body for chunk in chunks)
    assert chunks[0].snippet.startswith("A   REFUND")
