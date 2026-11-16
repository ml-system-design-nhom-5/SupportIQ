"""The routing configuration of a release: the values that routing reads (DATA-58).

The values are tuned on validation data for one model artifact version, and the file records
that version (DATA-58, ADR-0005 statement 5). Every tunable value of routing lives here, never
in code (ARCH-36).
"""

from dataclasses import dataclass
from enum import StrEnum

from supportiq_ai_service.suggestions.domain.request import IntentName


class AuthorityCategory(StrEnum):
    """What a sensitive term points to: an action that requires authority (FR-06, ESC-03)."""

    REFUND_DECISION = "refund_decision"
    TRANSACTION_DISPUTE = "transaction_dispute"
    POLICY_EXCEPTION = "policy_exception"
    LEGAL_CLAIM = "legal_claim"
    SUSPECTED_FRAUD = "suspected_fraud"


@dataclass(frozen=True, slots=True)
class SensitiveTerm:
    """A term of the sensitive-term list, reviewed by the policy owner and the RAG engineer.

    Attributes:
        term: Lowercase words; a message holds the term when it holds those whole words.
        category: What the term points to.
    """

    term: str
    category: AuthorityCategory


@dataclass(frozen=True, slots=True)
class RoutingConfiguration:
    """The routing configuration of one release (DATA-58).

    Attributes:
        version: The version of the configuration, which every result reports.
        model_version: The model artifact version that the values were tuned for.
        min_top_probability: τ, the minimum probability of the top intent (ESC-01).
        min_top_two_gap: δ, the minimum gap between the top two probabilities (ESC-01).
        rerank_weight: λ, the weight of the intent distribution in reranking (ADR-0005,
            statement 3).
        high_band_min_probability: The minimum probability of the `high` confidence band.
        sensitive_intents: The intents that require authority when they are likely enough
            (ADR-0005, statement 5).
        sensitive_intent_min_probability: The probability from which a sensitive intent
            counts, even when it is not first.
        sensitive_terms: The terms that require authority when a message holds one.
    """

    version: str
    model_version: str
    min_top_probability: float
    min_top_two_gap: float
    rerank_weight: float
    high_band_min_probability: float
    sensitive_intents: frozenset[IntentName]
    sensitive_intent_min_probability: float
    sensitive_terms: tuple[SensitiveTerm, ...]
