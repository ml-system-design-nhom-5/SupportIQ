"""The intent distribution is the softmax of the model's outputs, over every intent (FR-01)."""

import math

import pytest

from supportiq_ai_service.intent import IntentModelError
from supportiq_ai_service.intent.domain import distribution_from_logits

LABELS = ("track_order", "request_refund", "human_agent")


def test_the_distribution_is_the_softmax_of_the_outputs_most_likely_first() -> None:
    distribution = distribution_from_logits([0.0, math.log(3.0), 0.0], LABELS)

    assert [entry.label for entry in distribution.probabilities] == [
        "request_refund",
        "track_order",
        "human_agent",
    ]
    assert [entry.probability for entry in distribution.probabilities] == pytest.approx(
        [0.6, 0.2, 0.2]
    )
    assert math.fsum(entry.probability for entry in distribution.probabilities) == pytest.approx(1)


def test_equal_probabilities_keep_the_order_of_the_outputs() -> None:
    distribution = distribution_from_logits([1.0, 1.0, 1.0], LABELS)

    assert [entry.label for entry in distribution.probabilities] == list(LABELS)


def test_large_outputs_do_not_overflow() -> None:
    distribution = distribution_from_logits([1000.0, 1000.0, -1000.0], LABELS)

    assert distribution.probability_of("track_order") == pytest.approx(0.5)
    assert distribution.probability_of("human_agent") == pytest.approx(0)


def test_an_intent_outside_the_distribution_has_probability_0() -> None:
    distribution = distribution_from_logits([0.0, 0.0, 0.0], LABELS)

    assert distribution.probability_of("cancel_order") == 0


@pytest.mark.parametrize(
    "logits",
    [[0.0, 1.0], [0.0, 1.0, 2.0, 3.0], [0.0, math.nan, 0.0], [0.0, math.inf, 0.0], []],
)
def test_an_output_that_is_not_one_finite_score_for_each_intent_is_refused(
    logits: list[float],
) -> None:
    with pytest.raises(IntentModelError):
        distribution_from_logits(logits, LABELS if logits else ())
