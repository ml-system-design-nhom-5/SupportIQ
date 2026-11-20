"""How a KB document version is cut into passages for the index, as `main` cut it.

A chunk holds at most `max_tokens` tokens of the body, and two chunks in a row share
`overlap_tokens` tokens (`index.json`, README.md, Asset formats). The encoder embeds the title,
a newline, and the passage. Unlike `main`, which decoded token IDs back into text, a chunk keeps
the characters of the body from its first token to its last, so every snippet is a passage of
the body, as `KbDocumentVersion` requires.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.retrieval.domain import KbDocument

# The character span of each token of a text, without special tokens.
type TokenSpans = Callable[[str], Sequence[tuple[int, int]]]

# The values of `main`: the passage of a chunk keeps at least 50 tokens however long the title
# is, and the title takes two tokens more than its own for the newline and a margin.
_MIN_PASSAGE_TOKENS = 50
_TITLE_EXTRA_TOKENS = 2


@dataclass(frozen=True, slots=True)
class Chunk:
    """One passage of a KB document version, as the index holds it.

    Attributes:
        document: The document version.
        ordinal: The position of the chunk in the document, from 0.
        snippet: The passage, exactly as the body holds it.
        text: What the encoder embeds: the title, a newline, and the passage.
        token_count: The number of tokens of the text, without special tokens.
    """

    document: KbDocument
    ordinal: int
    snippet: str
    text: str
    token_count: int


def chunk_document(
    document: KbDocument, token_spans: TokenSpans, max_tokens: int, overlap_tokens: int
) -> tuple[Chunk, ...]:
    """Cut one document version into chunks.

    Args:
        document: The document version.
        token_spans: The tokenizer of the encoder, as the span of each token.
        max_tokens: The number of tokens of a chunk, title included.
        overlap_tokens: The number of tokens that two chunks in a row share.

    Returns:
        The chunks, in the order of the body; one chunk when the body is short.
    """
    title = document.title.strip()
    passage_tokens = max(
        _MIN_PASSAGE_TOKENS, max_tokens - len(token_spans(title)) - _TITLE_EXTRA_TOKENS
    )
    spans = token_spans(document.body)
    if not spans:
        return (_chunk(document, 0, document.body, title, token_spans),)
    step = max(1, passage_tokens - overlap_tokens)
    chunks: list[Chunk] = []
    first = 0
    # The last chunk is the one that reaches the last token of the body.
    while True:
        window = spans[first : first + passage_tokens]
        snippet = document.body[window[0][0] : window[-1][1]]
        chunks.append(_chunk(document, len(chunks), snippet, title, token_spans))
        if first + passage_tokens >= len(spans):
            return tuple(chunks)
        first += step


def _chunk(
    document: KbDocument, ordinal: int, snippet: str, title: str, token_spans: TokenSpans
) -> Chunk:
    text = f"{title}\n{snippet}"
    return Chunk(
        document=document,
        ordinal=ordinal,
        snippet=snippet,
        text=text,
        token_count=len(token_spans(text)),
    )
