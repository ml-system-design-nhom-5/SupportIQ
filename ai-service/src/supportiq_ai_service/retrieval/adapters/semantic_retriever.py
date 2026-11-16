"""The semantic search of the KB of a release, with the index and the encoder of `main`.

It searches by the content of the message only: the predicted intent never reaches it, and
no intent skips it (ADR-0005, statement 1). The early return of `main` for `human_agent`, its
in-code filter of one payment policy, and its intent boost are gone: routing reads the intent,
and reranking with λ comes after the search (ADR-0005, statement 3). The KB is ingested before
the release, so this module neither filters nor quarantines documents (ADR-0021, KB ingestion).
"""

from collections.abc import Sequence

from supportiq_ai_service.retrieval.adapters.in_memory_index import (
    InMemoryIndex,
    TextEncoder,
    build_index,
)
from supportiq_ai_service.retrieval.adapters.index_file import IndexConfiguration
from supportiq_ai_service.retrieval.domain import DocumentMatch, KbDocument


class SemanticRetriever:
    """Implement the `DocumentSearch` port with the in-memory index of a release."""

    def __init__(
        self,
        index: InMemoryIndex,
        encoder: TextEncoder,
        relevance_min_score: float,
        max_chunks_per_document: int,
    ) -> None:
        """Keep the index and how it is searched.

        Args:
            index: The index of the KB of the release.
            encoder: The encoder that built it.
            relevance_min_score: The minimum similarity of a relevant passage, from the index.
            max_chunks_per_document: The number of passages kept for each version.
        """
        self._index = index
        self._encoder = encoder
        self._relevance_min_score = relevance_min_score
        self._max_chunks_per_document = max_chunks_per_document

    def search(self, message: str) -> tuple[DocumentMatch, ...]:
        """Find the document versions relevant to a message.

        Args:
            message: The pseudonymized message. Confidential.

        Returns:
            Every relevant version, best match first; none when nothing is relevant.

        Raises:
            RetrievalError: The encoder failed.
        """
        if not self._index.chunks:
            return ()
        return self._index.search(
            self._encoder.encode_query(message),
            self._relevance_min_score,
            self._max_chunks_per_document,
        )


def build_semantic_retriever(
    documents: Sequence[KbDocument],
    encoder: TextEncoder,
    configuration: IndexConfiguration,
    max_chunks_per_document: int,
) -> SemanticRetriever:
    """Build the index of a release at startup and the search over it.

    Args:
        documents: The KB document versions of the release, possibly none.
        encoder: The encoder of the index asset.
        configuration: The configuration of the index asset.
        max_chunks_per_document: The number of passages kept for each version.

    Returns:
        The search.

    Raises:
        RetrievalError: The encoder failed while it embedded the KB.
    """
    index = build_index(
        documents,
        encoder,
        configuration.chunk_max_tokens,
        configuration.chunk_overlap_tokens,
    )
    return SemanticRetriever(
        index, encoder, configuration.relevance_min_score, max_chunks_per_document
    )
