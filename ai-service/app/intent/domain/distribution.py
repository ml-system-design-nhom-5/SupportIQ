"""The intent distribution of one message, and the port of the model that computes it (FR-01).

The distribution covers every intent label, so routing reads the probability of any intent,
not only the top one (ADR-0005, statements 3 and 5). In the first release it is the softmax of
the model's outputs, not calibrated (README.md, Known limits).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import ClassVar, Protocol

from app.platform import AiServiceError, ErrorCode


@dataclass(frozen=True, slots=True)
class IntentProbability:
    """The probability of one intent.

    Attributes:
        label: The intent label.
        probability: Its probability, from 0 to 1.
    """

    label: str
    probability: float


@dataclass(frozen=True, slots=True)
class IntentDistribution:
    """The probability of every intent for one message, most likely first.

    Attributes:
        probabilities: One entry for each intent label, most likely first; equal probabilities
            keep the order of the model's outputs.
    """

    probabilities: tuple[IntentProbability, ...]

    def probability_of(self, label: str) -> float:
        """Return the probability of one intent.

        Args:
            label: The intent label.

        Returns:
            Its probability, or 0 for a label that the distribution does not hold.
        """
        return next(
            (entry.probability for entry in self.probabilities if entry.label == label), 0.0
        )


class IntentModelError(AiServiceError):
    """The intent model returned an output that is not a score for every intent."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self) -> None:
        """Build the error with its fixed detail."""
        super().__init__("The intent model returned an invalid output.")


class IntentClassifier(Protocol):
    """Compute the intent distribution of a message."""

    def classify(self, message: str) -> IntentDistribution:
        """Classify one message.

        Args:
            message: The pseudonymized message. Confidential.

        Returns:
            The probability of every intent.

        Raises:
            IntentModelError: The model returned an invalid output.
        """
        ...


def distribution_from_logits(logits: Sequence[float], labels: Sequence[str]) -> IntentDistribution:
    """Turn the outputs of a classifier into the probability of each intent, with a softmax.

    Args:
        logits: The output of the model for each label, by index.
        labels: The intent label of each output.

    Returns:
        The distribution, most likely first.

    Raises:
        IntentModelError: There is not one finite output for each label.
    """
    if not labels or len(logits) != len(labels) or not all(map(math.isfinite, logits)):
        raise IntentModelError
    # Subtracting the largest output keeps every exponent at most 0, so none overflows.
    largest = max(logits)
    weights = [math.exp(logit - largest) for logit in logits]
    total = math.fsum(weights)
    probabilities = [
        IntentProbability(label=label, probability=weight / total)
        for label, weight in zip(labels, weights, strict=True)
    ]
    # `sorted` is stable, so equal probabilities keep the order of the outputs.
    return IntentDistribution(
        probabilities=tuple(sorted(probabilities, key=lambda entry: -entry.probability))
    )
