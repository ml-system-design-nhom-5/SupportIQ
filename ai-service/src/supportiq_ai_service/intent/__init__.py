"""Public API of intent: the labels, the distribution, and the port of the model (ARCH-17)."""

from supportiq_ai_service.intent.domain import (
    INTENT_LABELS,
    IntentClassifier,
    IntentDistribution,
    IntentModelError,
    IntentProbability,
)

__all__ = [
    "INTENT_LABELS",
    "IntentClassifier",
    "IntentDistribution",
    "IntentModelError",
    "IntentProbability",
]
