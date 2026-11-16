"""In-memory fakes of the retrieval ports and of the encoder of the index (ARCH-27).

`EXAMPLE_DOCUMENT` is `contracts/examples/getKbDocumentVersion/found.json`.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType

import numpy as np

from supportiq_ai_service.release import LoadedRelease
from supportiq_ai_service.retrieval import KbDocument, RetrievalError
from supportiq_ai_service.retrieval.adapters.in_memory_index import Vectors, l2_normalized

EXAMPLE_DOCUMENT = KbDocument(
    document_id="SAMPLE-REFUND-001",
    version="1.0",
    title="Sample refund document",
    body=(
        "This is sample text. It is not KB content and not a policy. The document version "
        "opens here in full, so staff can check a citation against its source."
    ),
    policy_key="sample_refund_review",
    effective_start_at=datetime(2026, 1, 1, tzinfo=UTC),
    effective_end_at=None,
    owner="Policy owner",
    source="Sample source document",
    last_reviewed_at=None,
)


def _example_documents() -> Mapping[tuple[str, str], KbDocument]:
    key = (EXAMPLE_DOCUMENT.document_id, EXAMPLE_DOCUMENT.version)
    return MappingProxyType({key: EXAMPLE_DOCUMENT})


@dataclass(frozen=True, slots=True)
class StaticKbDocuments:
    """A KB whose document versions a test chooses, by document ID and version."""

    documents: Mapping[tuple[str, str], KbDocument] = field(default_factory=_example_documents)

    def find(self, document_id: str, version: str, release: LoadedRelease) -> KbDocument | None:
        """Return the chosen document version, or None.

        Args:
            document_id: The document.
            version: The version of the document.
            release: The loaded release.
        """
        del release
        return self.documents.get((document_id, version))


# Words of a text for the fake encoder: every run of characters other than spaces.
_WORD = re.compile(r"\S+")


@dataclass(slots=True)
class KeywordEncoder:
    """An encoder whose vector counts some keywords, so a test knows what is similar.

    The last dimension is 1 only for a text without any keyword, so no text has a vector of 0
    and texts without a keyword are similar to no text with one. Each token is a word, at its
    place in the text.
    """

    keywords: tuple[str, ...] = ("refund", "delivery", "card")
    query_count: int = 0

    def token_spans(self, text: str) -> Sequence[tuple[int, int]]:
        """Return the span of each word."""
        return tuple(match.span() for match in _WORD.finditer(text))

    def encode_passages(self, texts: Sequence[str]) -> Vectors:
        """Embed each text by its keyword counts."""
        return l2_normalized(np.array([self._counts(text) for text in texts], dtype=np.float32))

    def encode_query(self, text: str) -> Vectors:
        """Embed one query by its keyword counts, and count the queries."""
        self.query_count += 1
        return self.encode_passages([text])[0]

    def _counts(self, text: str) -> list[float]:
        words = [word.lower().strip(".,") for word in _WORD.findall(text)]
        counts = [float(words.count(keyword)) for keyword in self.keywords]
        return [*counts, 0.0 if any(counts) else 1.0]


class FailingEncoder(KeywordEncoder):
    """An encoder that embeds the KB but fails on every query, as a broken model would."""

    def encode_query(self, text: str) -> Vectors:
        """Fail.

        Raises:
            RetrievalError: Always.
        """
        del text
        raise RetrievalError
