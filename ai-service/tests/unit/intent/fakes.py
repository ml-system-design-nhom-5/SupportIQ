"""Intent distributions for tests that need no model weights."""

from supportiq_ai_service.intent import INTENT_LABELS, IntentDistribution, IntentProbability


def distribution(*entries: tuple[str, float]) -> IntentDistribution:
    """Return a distribution with the given probabilities first, and 0 for every other label.

    Args:
        *entries: The labels and their probabilities, most likely first.

    Returns:
        The distribution over every intent.
    """
    given = dict(entries)
    return IntentDistribution(
        (
            *(IntentProbability(label, probability) for label, probability in entries),
            *(IntentProbability(label, 0.0) for label in INTENT_LABELS if label not in given),
        )
    )
