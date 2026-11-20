"""The grounding check of a written draft, before staff see it (FR-03, ADR-0014, TEST-26).

A draft passes only when every statement of a policy or a fact cites a source of the right
kind: a policy cites a valid KB document version, and a fact about the order cites a field of
the order context sent with the request and repeats its value (ADR-0014, statements 2 and 4).
A placeholder that the message does not hold makes the output invalid (ADR-0010). A draft that
fails is never shown: the outcome carries the reason code (ESC-05).
"""

import re

from app.drafting import DraftRequest, OrderFact, PolicySource, WrittenDraft
from app.suggestions.domain.analysis import ReasonCode
from app.suggestions.domain.draft import (
    Citation,
    Draft,
    DraftSegment,
    KbDocumentCitation,
    OrderContextCitation,
    OrderFieldName,
)
from app.suggestions.domain.masking import placeholders_in

GROUNDING_FAILED = ReasonCode("grounding_failed")
LLM_INVALID_OUTPUT = ReasonCode("llm_invalid_output")
_CITATION = re.compile(r"\[(S\d+)\]")
# A citation with the spaces before it, which go with it when it is removed.
_CITATION_WITH_SPACES = re.compile(r"\s*\[S\d+\]")
# The longest draft of the contract, its segments joined as `backend` joins them (`Draft`).
MAX_DRAFT_CHARS = 2_000
_PARAGRAPH_SEPARATOR = "\n\n"
_PARAGRAPH_BREAK = re.compile(r"\n\s*\n")
# A statement that needs a source: an amount, a period, or a term of refunds, returns, fees,
# or warranties (the pattern of `main`).
_FACTUAL_COMMITMENT = re.compile(
    r"(\$\s*\d+|\b\d+\s*(days?|business days?|hours?|weeks?|months?)\b"
    r"|\b(refund|refunded|refunds|return window|fee|fees|warranty)\b)",
    re.IGNORECASE,
)
# Wording that states a policy rather than a fact of the order. An order field never supports
# a policy (ADR-0014, statement 2); this pattern is a heuristic (README.md, Known limits).
_POLICY_CLAIM = re.compile(
    r"\b(polic(?:y|ies)|eligib\w*|entitle\w*|return window|refundable|non-refundable"
    r"|fees?|warrant(?:y|ies)|guarantee\w*"
    r"|within \d+ (?:business |working )?(?:hours?|days?|weeks?|months?))\b",
    re.IGNORECASE,
)

type _Source = PolicySource | OrderFact


class DraftCheckError(Exception):
    """A written draft failed its check, so it is never shown (ESC-05)."""

    def __init__(self, reason_code: ReasonCode) -> None:
        """Keep the reason code of the outcome.

        Args:
            reason_code: `grounding_failed` or `llm_invalid_output`.
        """
        super().__init__(reason_code)
        self.reason_code = reason_code


def check_draft(
    written: WrittenDraft, request: DraftRequest, uncited_segment_max_chars: int
) -> Draft:
    """Check a written draft against the sources that its request sent.

    Args:
        written: The draft that the LLM wrote.
        request: What the LLM received.
        uncited_segment_max_chars: The longest segment that may go without a citation, such as
            a greeting; any statement of a fact needs one whatever its length.

    Returns:
        The draft as segments with their citations.

    Raises:
        DraftCheckError: The draft holds a placeholder that the message does not hold
            (`llm_invalid_output`), or a statement without the right source (`grounding_failed`).
    """
    if not placeholders_in(written.text) <= placeholders_in(request.message):
        raise DraftCheckError(LLM_INVALID_OUTPUT)
    sources: dict[str, _Source] = {
        source.source_id: source for source in (*request.policy_sources, *request.order_facts)
    }
    inline = _CITATION.findall(written.text)
    if (
        not set(inline) <= sources.keys()
        or set(written.cited_source_ids) != set(inline)
        or not (inline or written.is_clarification)
    ):
        raise DraftCheckError(GROUNDING_FAILED)
    paragraphs = [part for part in _PARAGRAPH_BREAK.split(written.text) if part.strip()]
    segments = tuple(
        _segment(index, paragraph, sources, written.is_clarification, uncited_segment_max_chars)
        for index, paragraph in enumerate(paragraphs)
    )
    if len(_PARAGRAPH_SEPARATOR.join(segment.text for segment in segments)) > MAX_DRAFT_CHARS:
        raise DraftCheckError(LLM_INVALID_OUTPUT)
    cited = list(dict.fromkeys(inline))
    return Draft(segments=segments, citations=tuple(_citation(sources[key]) for key in cited))


def _segment(
    index: int,
    paragraph: str,
    sources: dict[str, _Source],
    is_clarification: bool,
    uncited_max_chars: int,
) -> DraftSegment:
    ids = tuple(dict.fromkeys(_CITATION.findall(paragraph)))
    text = " ".join(_CITATION_WITH_SPACES.sub("", paragraph).split())
    if not text:
        raise DraftCheckError(GROUNDING_FAILED)
    if not ids:
        too_long = not is_clarification and len(text) > uncited_max_chars
        if too_long or _FACTUAL_COMMITMENT.search(text):
            raise DraftCheckError(GROUNDING_FAILED)
    facts = [source for key in ids if isinstance(source := sources[key], OrderFact)]
    if not all(_states_value(text, fact.value) for fact in facts):
        raise DraftCheckError(GROUNDING_FAILED)
    if facts and len(facts) == len(ids) and _POLICY_CLAIM.search(text):
        raise DraftCheckError(GROUNDING_FAILED)
    return DraftSegment(
        segment_id=f"segment-{index + 1}", paragraph_index=index, text=text, citation_ids=ids
    )


def _states_value(text: str, value: str) -> bool:
    # The whole value, in any case, with no letter or digit joined to it on either side.
    pattern = r"(?<!\w)" + re.escape(value) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _citation(source: _Source) -> Citation:
    if isinstance(source, OrderFact):
        return OrderContextCitation(
            citation_id=source.source_id, field=OrderFieldName(source.field)
        )
    return KbDocumentCitation(
        citation_id=source.source_id,
        document_id=source.document_id,
        version=source.version,
        snippet=source.snippet,
    )
