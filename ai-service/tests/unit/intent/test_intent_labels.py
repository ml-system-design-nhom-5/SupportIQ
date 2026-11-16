"""The intent labels of the domain are the 46 labels of the contract, in its order."""

from supportiq_ai_service.generated import IntentLabel
from supportiq_ai_service.intent import INTENT_LABELS

# The number of Bitext intents (glossary: Intent).
BITEXT_INTENT_COUNT = 46


def test_the_intent_labels_are_those_of_the_contract() -> None:
    assert tuple(label.value for label in IntentLabel) == INTENT_LABELS
    assert len(INTENT_LABELS) == BITEXT_INTENT_COUNT
