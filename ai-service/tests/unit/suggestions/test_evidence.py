"""Each relevant version gets its validity at as_of before the top documents are chosen."""

import dataclasses
from datetime import UTC, datetime
from types import MappingProxyType

from supportiq_ai_service.retrieval import DocumentMatch
from supportiq_ai_service.suggestions.domain import DocumentIntents, DocumentValidity, IntentName
from supportiq_ai_service.suggestions.domain.evidence import (
    CONFLICTING_SOURCES,
    NO_VALID_DOCUMENT,
    ONLY_EXPIRED_DOCUMENTS,
    Ranking,
    assess_evidence,
)
from tests.unit.retrieval.fakes import EXAMPLE_DOCUMENT

AS_OF = datetime(2026, 11, 5, 9, 30, tzinfo=UTC)
REFUND = dataclasses.replace(EXAMPLE_DOCUMENT, document_id="REFUND", policy_key="refund_window")
DELIVERY = dataclasses.replace(EXAMPLE_DOCUMENT, document_id="DELIVERY", policy_key="delivery")
EXPIRED = dataclasses.replace(
    REFUND, version="0.9", effective_end_at=datetime(2026, 1, 1, tzinfo=UTC)
)
FUTURE = dataclasses.replace(
    DELIVERY, version="2.0", effective_start_at=datetime(2027, 1, 1, tzinfo=UTC)
)
SECOND_REFUND = dataclasses.replace(REFUND, document_id="REFUND-B")
MAPPING = DocumentIntents(
    MappingProxyType(
        {
            ("REFUND", "1.0"): frozenset({IntentName("request_refund")}),
            ("DELIVERY", "1.0"): frozenset(
                {IntentName("track_order"), IntentName("delivery_time")}
            ),
        }
    )
)
PROBABILITIES = {"track_order": 0.5, "delivery_time": 0.2, "request_refund": 0.3}


def _match(document: object, score: float) -> DocumentMatch:
    assert isinstance(document, type(EXAMPLE_DOCUMENT))
    return DocumentMatch(document=document, score=score, snippets=(document.body,))


def _ranking(
    top_intent: str = "track_order", rerank_weight: float = 0.0, top_k: int = 3
) -> Ranking:
    return Ranking(
        mapping=MAPPING,
        probability_of=lambda intent: PROBABILITIES.get(intent, 0.0),
        top_intent=IntentName(top_intent),
        rerank_weight=rerank_weight,
        top_k=top_k,
    )


def test_each_version_gets_its_validity_and_a_version_from_the_future_is_left_out() -> None:
    evidence = assess_evidence(
        (_match(DELIVERY, 0.9), _match(EXPIRED, 0.8), _match(FUTURE, 0.95)), AS_OF, _ranking()
    )

    assert [(ranked.document, ranked.validity) for ranked in evidence.documents] == [
        (DELIVERY, DocumentValidity.VALID),
        (EXPIRED, DocumentValidity.EXPIRED),
    ]
    assert evidence.reason_codes == frozenset()
    assert evidence.valid_documents()[0].document == DELIVERY


def test_a_version_that_ends_at_as_of_has_expired() -> None:
    ending = dataclasses.replace(DELIVERY, effective_end_at=AS_OF)

    (ranked,) = assess_evidence((_match(ending, 0.9),), AS_OF, _ranking()).documents

    assert ranked.validity is DocumentValidity.EXPIRED


def test_two_versions_in_effect_with_one_policy_key_conflict_and_abstain() -> None:
    evidence = assess_evidence(
        (_match(REFUND, 0.9), _match(SECOND_REFUND, 0.8), _match(DELIVERY, 0.7)), AS_OF, _ranking()
    )

    assert [ranked.validity for ranked in evidence.documents] == [
        DocumentValidity.CONFLICTING,
        DocumentValidity.CONFLICTING,
        DocumentValidity.VALID,
    ]
    assert evidence.reason_codes == {CONFLICTING_SOURCES}
    assert [ranked.document for ranked in evidence.valid_documents()] == [DELIVERY]


def test_only_expired_versions_or_none_at_all_abstain() -> None:
    expired = assess_evidence((_match(EXPIRED, 0.9),), AS_OF, _ranking())
    nothing = assess_evidence((), AS_OF, _ranking())

    assert expired.reason_codes == {ONLY_EXPIRED_DOCUMENTS}
    assert nothing.reason_codes == {NO_VALID_DOCUMENT}
    assert nothing.disagreement is False


def test_reranking_adds_lambda_times_the_probability_of_the_mapped_intents() -> None:
    evidence = assess_evidence(
        (_match(REFUND, 0.8), _match(DELIVERY, 0.7)), AS_OF, _ranking(rerank_weight=0.5)
    )

    # REFUND: 0.8 + 0.5 x 0.3; DELIVERY: 0.7 + 0.5 x (0.5 + 0.2).
    assert [(ranked.document, ranked.score) for ranked in evidence.documents] == [
        (DELIVERY, 0.7 + 0.5 * 0.7),
        (REFUND, 0.8 + 0.5 * 0.3),
    ]


def test_only_the_top_k_documents_are_kept() -> None:
    evidence = assess_evidence(
        (_match(DELIVERY, 0.9), _match(REFUND, 0.8)), AS_OF, _ranking(top_k=1)
    )

    assert [ranked.document for ranked in evidence.documents] == [DELIVERY]


def test_no_top_document_mapped_to_the_top_intent_is_a_disagreement() -> None:
    agrees = assess_evidence((_match(REFUND, 0.9), _match(DELIVERY, 0.8)), AS_OF, _ranking())
    disagrees = assess_evidence((_match(REFUND, 0.9),), AS_OF, _ranking())
    unmapped = assess_evidence((_match(SECOND_REFUND, 0.9),), AS_OF, _ranking("request_refund"))

    assert (agrees.disagreement, disagrees.disagreement, unmapped.disagreement) == (
        False,
        True,
        True,
    )


def test_an_expired_version_never_pushes_a_version_in_effect_out_of_the_top_k() -> None:
    evidence = assess_evidence(
        (_match(EXPIRED, 0.9), _match(DELIVERY, 0.5)), AS_OF, _ranking(top_k=1)
    )

    assert [ranked.document for ranked in evidence.documents] == [DELIVERY]
    assert evidence.reason_codes == frozenset()


def test_a_version_that_starts_at_as_of_is_in_effect() -> None:
    starting = dataclasses.replace(DELIVERY, effective_start_at=AS_OF)

    (ranked,) = assess_evidence((_match(starting, 0.9),), AS_OF, _ranking()).documents

    assert ranked.validity is DocumentValidity.VALID
