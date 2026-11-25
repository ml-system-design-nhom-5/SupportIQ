"""A field of a release file that holds one of the 46 intent labels of the contract."""

from typing import Annotated

from pydantic import AfterValidator

from app.intent import INTENT_LABELS
from app.suggestions.domain import IntentName

_KNOWN_LABELS = frozenset(INTENT_LABELS)


def _known_label(label: IntentName) -> IntentName:
    if label not in _KNOWN_LABELS:
        message = "an intent is one of the 46 labels of `IntentLabel`"
        raise ValueError(message)
    return label


IntentLabelField = Annotated[IntentName, AfterValidator(_known_label)]
