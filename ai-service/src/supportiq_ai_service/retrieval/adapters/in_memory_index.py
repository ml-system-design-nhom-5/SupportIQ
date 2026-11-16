"""The in-memory index of `main`: exact cosine similarity over the passages of the KB of a release.

The vectors are L2-normalized, so a dot product is the cosine similarity. `ai-service` builds
the index at startup from the KB of its release and never changes it. A search keeps every
document version with a passage above the relevance score of the index, and at most a set
number of passages for each version, best first. Choosing the top documents comes later, after
validity and reranking (ADR-0005, statements 2 and 3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from supportiq_ai_service.retrieval.adapters.chunking import Chunk, TokenSpans, chunk_document
from supportiq_ai_service.retrieval.domain import DocumentMatch, KbDocument, RetrievalError

type Vectors = NDArray[np.float32]

_MATRIX_DIMENSIONS = 2


class TextEncoder(Protocol):
    """Embed texts as L2-normalized vectors, and tell where the tokens of a text are."""

    def token_spans(self, text: str) -> Sequence[tuple[int, int]]:
        """Return the character span of each token of a text, without special tokens."""
        ...

    def encode_passages(self, texts: Sequence[str]) -> Vectors:
        """Embed passages of the KB, one row for each.

        Raises:
            RetrievalError: The encoder failed.
        """
        ...

    def encode_query(self, text: str) -> Vectors:
        """Embed one query.

        Raises:
            RetrievalError: The encoder failed.
        """
        ...


def l2_normalized(vectors: NDArray[np.float32]) -> Vectors:
    """Scale each row to length 1, so a dot product is a cosine similarity.

    Args:
        vectors: The vectors, one row for each.

    Returns:
        The normalized vectors.

    Raises:
        RetrievalError: A vector is not finite, or is 0, so it has no direction.
    """
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    if not np.all(np.isfinite(vectors)) or not np.all(norms > 0):
        raise RetrievalError
    return (vectors / norms).astype(np.float32)


@dataclass(frozen=True, slots=True)
class InMemoryIndex:
    """The passages of a KB and their vectors, in the same order.

    Attributes:
        chunks: The passages.
        vectors: One L2-normalized vector for each passage.
    """

    chunks: tuple[Chunk, ...]
    vectors: Vectors

    def search(
        self, query: Vectors, relevance_min_score: float, max_chunks_per_document: int
    ) -> tuple[DocumentMatch, ...]:
        """Find the document versions with passages relevant to a query.

        Args:
            query: The L2-normalized vector of the query.
            relevance_min_score: The minimum similarity of a relevant passage.
            max_chunks_per_document: The number of passages kept for each version.

        Returns:
            Each relevant version with its best passages, best match first.

        Raises:
            RetrievalError: The query has another dimension than the index.
        """
        if not self.chunks:
            return ()
        if query.shape != (self.vectors.shape[1],):
            raise RetrievalError
        scores = self.vectors @ query
        snippets: dict[tuple[str, str], list[str]] = {}
        matches: dict[tuple[str, str], tuple[KbDocument, float]] = {}
        # A stable sort, so equal scores keep the order of the KB.
        order: list[int] = np.argsort(-scores, kind="stable").tolist()
        for position in order:
            score = float(scores[position])
            if score < relevance_min_score:
                break
            chunk = self.chunks[position]
            key = (chunk.document.document_id, chunk.document.version)
            kept = snippets.setdefault(key, [])
            matches.setdefault(key, (chunk.document, score))
            if len(kept) < max_chunks_per_document:
                kept.append(chunk.snippet)
        return tuple(
            DocumentMatch(document=document, score=score, snippets=tuple(snippets[key]))
            for key, (document, score) in matches.items()
        )


def build_index(
    documents: Sequence[KbDocument],
    encoder: TextEncoder,
    max_tokens: int,
    overlap_tokens: int,
) -> InMemoryIndex:
    """Cut every document version into passages and embed them.

    Args:
        documents: The KB document versions of the release, possibly none.
        encoder: The encoder of the index.
        max_tokens: The number of tokens of a chunk.
        overlap_tokens: The number of tokens that two chunks in a row share.

    Returns:
        The index.

    Raises:
        RetrievalError: The encoder failed, or returned another number of vectors than chunks.
    """
    token_spans: TokenSpans = encoder.token_spans
    chunks = tuple(
        chunk
        for document in documents
        for chunk in chunk_document(document, token_spans, max_tokens, overlap_tokens)
    )
    if not chunks:
        return InMemoryIndex(chunks=(), vectors=np.empty((0, 0), dtype=np.float32))
    vectors = encoder.encode_passages([chunk.text for chunk in chunks])
    if vectors.ndim != _MATRIX_DIMENSIONS or vectors.shape[0] != len(chunks):
        raise RetrievalError
    return InMemoryIndex(chunks=chunks, vectors=vectors)
