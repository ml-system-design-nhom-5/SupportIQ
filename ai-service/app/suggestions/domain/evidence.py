"""The evidence of a message: validity at `as_of`, reranking, and the top documents (ADR-0005).

Retrieval finds the relevant versions by content only (statement 1). Here each version gets
its validity at `as_of` before the top documents are chosen (statement 2): a version that
ended is `expired`; two versions in effect with the same policy key are `conflicting` and are
never cited; a version that starts after `as_of` is left out (contract `DocumentValidity`).
Reranking adds λ times the probability of the intents of each version, from the mapping file
(statements 3 and 6). Evidence decides only abstentions; an order citation is never evidence
for routing (ADR-0014, statement 3).
"""

from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.retrieval import DocumentMatch, KbDocument
from app.suggestions.domain.analysis import DocumentValidity, ReasonCode
from app.suggestions.domain.document_intents import DocumentIntents
from app.suggestions.domain.request import IntentName

NO_VALID_DOCUMENT = ReasonCode("no_valid_document")
ONLY_EXPIRED_DOCUMENTS = ReasonCode("only_expired_documents")
CONFLICTING_SOURCES = ReasonCode("conflicting_sources")


@dataclass(frozen=True, slots=True)
class RankedVersion:
    """A relevant KB document version, with its validity and its reranked score.

    Attributes:
        document: The document version.
        validity: Whether it may support a reply at `as_of`.
        score: The retrieval score plus λ times the probability of its intents.
        snippets: Its matching passages, best first.
    """

    document: KbDocument
    validity: DocumentValidity
    score: float
    snippets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Evidence:
    """What retrieval found for a message, after validity and reranking.

    Attributes:
        documents: The top documents, whatever their validity, best first.
        reason_codes: `no_valid_document`, `only_expired_documents`, or `conflicting_sources`,
            each of which ends in an abstention (ESC-04); empty when a valid document exists.
        disagreement: Whether no top document maps to the top intent, which is a warning and
            lowers the band (statement 4).
    """

    documents: tuple[RankedVersion, ...]
    reason_codes: frozenset[ReasonCode]
    disagreement: bool

    def valid_documents(self) -> tuple[RankedVersion, ...]:
        """Return the top documents that a draft may cite.

        Returns:
            The valid documents, best first.
        """
        return tuple(
            ranked for ranked in self.documents if ranked.validity is DocumentValidity.VALID
        )


@dataclass(frozen=True, slots=True)
class Ranking:
    """How the matches of one message are reranked and cut (ADR-0005, statements 3 and 4).

    Attributes:
        mapping: The intents of each version.
        probability_of: The probability of an intent, from the distribution or the staff choice.
        top_intent: The intent of the message, for the disagreement check.
        rerank_weight: λ of the routing configuration.
        top_k: The number of top documents.
    """

    mapping: DocumentIntents
    probability_of: Callable[[IntentName], float]
    top_intent: IntentName
    rerank_weight: float
    top_k: int


def assess_evidence(
    matches: tuple[DocumentMatch, ...], as_of: datetime, ranking: Ranking
) -> Evidence:
    """Give each match its validity, rerank the matches, and keep the top documents.

    Args:
        matches: The relevant versions that retrieval found, by content only.
        as_of: The time at which validity is evaluated.
        ranking: How the matches are reranked and cut.

    Returns:
        The top documents and what they mean for routing.
    """
    mapping = ranking.mapping
    in_effect_or_ended = [match for match in matches if match.document.effective_start_at <= as_of]
    in_effect = [
        match.document for match in in_effect_or_ended if _in_effect(match.document, as_of)
    ]
    keys = Counter(document.policy_key for document in in_effect)
    ranked = [
        RankedVersion(
            document=match.document,
            validity=_validity(match.document, as_of, keys),
            score=match.score
            + ranking.rerank_weight
            * sum(
                ranking.probability_of(intent)
                for intent in mapping.intents_of(match.document.document_id, match.document.version)
            ),
            snippets=match.snippets,
        )
        for match in in_effect_or_ended
    ]
    # Versions in effect come first, so an expired version never pushes one out of the top
    # documents; expired versions only fill the places left. The sort is stable, so equal
    # scores keep the order of retrieval.
    documents = tuple(
        sorted(
            ranked,
            key=lambda version: (version.validity is DocumentValidity.EXPIRED, -version.score),
        )[: ranking.top_k]
    )
    return Evidence(
        documents=documents,
        reason_codes=_reason_codes(documents),
        disagreement=bool(documents)
        and not any(
            ranking.top_intent
            in mapping.intents_of(version.document.document_id, version.document.version)
            for version in documents
        ),
    )


def _in_effect(document: KbDocument, as_of: datetime) -> bool:
    end = document.effective_end_at
    return document.effective_start_at <= as_of and (end is None or as_of < end)


def _validity(document: KbDocument, as_of: datetime, keys: Counter[str]) -> DocumentValidity:
    if not _in_effect(document, as_of):
        return DocumentValidity.EXPIRED
    if keys[document.policy_key] > 1:
        return DocumentValidity.CONFLICTING
    return DocumentValidity.VALID


def _reason_codes(documents: tuple[RankedVersion, ...]) -> frozenset[ReasonCode]:
    validities = {version.validity for version in documents}
    if DocumentValidity.CONFLICTING in validities:
        return frozenset({CONFLICTING_SOURCES})
    if DocumentValidity.VALID in validities:
        return frozenset()
    if DocumentValidity.EXPIRED in validities:
        return frozenset({ONLY_EXPIRED_DOCUMENTS})
    return frozenset({NO_VALID_DOCUMENT})
