"""The ports of the gate: the real model and search, unless the case injects a part."""

import pytest
from app.drafting import DraftRequest, LlmCallError, LlmFailure
from app.intent import (
    IntentClassifier,
    IntentDistribution,
    IntentModelError,
    IntentProbability,
)
from app.retrieval import DocumentSearch, RetrievalError

from supportiq_release.gate.adapters import GatePorts
from supportiq_release.gate.domain import Failure, Injection
from tests.unit.gate.fakes import FAKE_DISTRIBUTION, FAKE_LABELS, FakeClassifier, FakeSearch

LABELS = (*FAKE_LABELS, "cancel_order", "delivery_issue")
MESSAGE = "Where is [ORDER_ID_1] now?"
REQUEST = DraftRequest(MESSAGE, "track_order", (), (), False)
# Probabilities at the thresholds τ and the sensitive minimum, as the cases at a threshold have.
AT_TAU = 0.70
AT_SENSITIVE_MINIMUM = 0.10
LIKELY = 0.93


def _ports(labels: tuple[str, ...] = LABELS) -> tuple[GatePorts, IntentClassifier, DocumentSearch]:
    ports = GatePorts(labels=labels)
    candidate = ports.candidate_ports()
    return ports, candidate.classifier(FakeClassifier()), candidate.search(FakeSearch())


def _real_distribution() -> IntentDistribution:
    return FakeClassifier().classify(MESSAGE)


def _distribution(*listed: tuple[str, float]) -> Injection:
    return Injection(intent_distribution=listed, failure=None)


def _failure(failure: Failure) -> Injection:
    return Injection(intent_distribution=None, failure=failure)


def test_without_an_injection_the_real_model_and_search_answer() -> None:
    ports, classifier, search = _ports()

    assert ports.injection is None
    assert classifier.classify(MESSAGE) == _real_distribution()
    assert search.search(MESSAGE) == ()


def test_an_injected_distribution_keeps_its_listed_probabilities_exactly() -> None:
    ports, classifier, _search = _ports()
    ports.use(_distribution(("track_order", AT_TAU), ("cancel_order", AT_SENSITIVE_MINIMUM)))

    distribution = classifier.classify(MESSAGE)

    assert distribution.probability_of("track_order") == AT_TAU
    assert distribution.probability_of("cancel_order") == AT_SENSITIVE_MINIMUM


def test_an_injected_distribution_covers_every_label_once_and_shares_the_rest_equally() -> None:
    ports, classifier, _search = _ports()
    ports.use(_distribution(("track_order", AT_TAU), ("cancel_order", AT_SENSITIVE_MINIMUM)))

    distribution = classifier.classify(MESSAGE)

    labels = [entry.label for entry in distribution.probabilities]
    assert sorted(labels) == sorted(LABELS)
    shares = [
        entry.probability
        for entry in distribution.probabilities
        if entry.label not in {"track_order", "cancel_order"}
    ]
    others = len(LABELS) - 2
    assert len(shares) == others
    assert len(set(shares)) == 1
    assert shares[0] == pytest.approx((1 - AT_TAU - AT_SENSITIVE_MINIMUM) / others)
    assert sum(entry.probability for entry in distribution.probabilities) == pytest.approx(1)


def test_an_injected_distribution_is_most_likely_first() -> None:
    ports, classifier, _search = _ports()
    ports.use(_distribution(("cancel_order", 0.10), ("delivery_issue", 0.76)))

    distribution = classifier.classify(MESSAGE)

    probabilities = [entry.probability for entry in distribution.probabilities]
    assert probabilities == sorted(probabilities, reverse=True)
    assert distribution.probabilities[0] == IntentProbability("delivery_issue", 0.76)
    assert distribution.probabilities[1] == IntentProbability("cancel_order", 0.10)


def test_a_listed_intent_stays_before_an_equal_share() -> None:
    # Three labels share 0.75 equally, so each gets 0.25, as much as the listed intent.
    labels = ("track_order", "cancel_order", "human_agent", "delivery_issue")
    ports, classifier, _search = _ports(labels)
    ports.use(_distribution(("human_agent", 0.25)))

    distribution = classifier.classify(MESSAGE)

    assert [entry.label for entry in distribution.probabilities] == [
        "human_agent",
        "track_order",
        "cancel_order",
        "delivery_issue",
    ]
    assert [entry.probability for entry in distribution.probabilities] == [0.25] * 4


def test_a_failure_of_the_intent_model_fails_the_classifier_only() -> None:
    ports, classifier, search = _ports()
    ports.use(_failure(Failure.INTENT_MODEL))

    with pytest.raises(IntentModelError):
        classifier.classify(MESSAGE)
    assert search.search(MESSAGE) == ()


def test_a_failure_of_the_search_fails_the_search_only() -> None:
    ports, classifier, search = _ports()
    ports.use(_failure(Failure.RETRIEVAL))

    with pytest.raises(RetrievalError):
        search.search(MESSAGE)
    assert classifier.classify(MESSAGE) == _real_distribution()


def test_a_failure_of_the_llm_leaves_the_model_and_the_search_real() -> None:
    ports, classifier, search = _ports()
    ports.use(_failure(Failure.LLM))

    assert classifier.classify(MESSAGE) == _real_distribution()
    assert search.search(MESSAGE) == ()


def test_a_failure_with_a_distribution_gives_the_distribution_and_fails_the_named_part() -> None:
    ports, classifier, search = _ports()
    ports.use(Injection(intent_distribution=(("track_order", LIKELY),), failure=Failure.RETRIEVAL))

    assert classifier.classify(MESSAGE).probability_of("track_order") == LIKELY
    with pytest.raises(RetrievalError):
        search.search(MESSAGE)


def test_use_none_restores_the_real_model_and_search() -> None:
    ports, classifier, search = _ports()
    ports.use(_failure(Failure.INTENT_MODEL))
    ports.use(_failure(Failure.RETRIEVAL))

    ports.use(None)

    assert ports.injection is None
    assert classifier.classify(MESSAGE) == _real_distribution()
    assert search.search(MESSAGE) == ()


@pytest.mark.parametrize(
    "injection",
    [None, _failure(Failure.LLM), _distribution(("track_order", LIKELY))],
    ids=["no-injection", "llm-failure", "distribution"],
)
def test_the_writer_counts_every_call_and_fails_it_as_unavailable(
    injection: Injection | None,
) -> None:
    ports = GatePorts(labels=LABELS)
    ports.use(injection)
    writer = ports.candidate_ports().writer

    for call in (1, 2):
        with pytest.raises(LlmCallError) as failed:
            writer.write(REQUEST)
        assert failed.value.failure is LlmFailure.UNAVAILABLE
        assert ports.llm_calls == call


def test_the_fake_distribution_is_the_real_answer_of_the_tests() -> None:
    # Guards the assertions above: the real fake model never gives an injected distribution.
    assert (
        tuple((entry.label, entry.probability) for entry in _real_distribution().probabilities)
        == FAKE_DISTRIBUTION
    )
