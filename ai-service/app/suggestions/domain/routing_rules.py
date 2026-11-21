"""The one routing of `ai-service`: the intent, the authority flag, and the recommendation.

Routing reads only the intent distribution, the evidence, and the routing configuration of the
release (ADR-0021, ADR-0005 statement 5, DATA-58). It recommends; staff decide (FR-04). The
heuristics of `main` that set codes with another meaning than the contract, or that named KB
documents, are gone (README.md, Known limits).
"""

import re
from dataclasses import dataclass

from app.intent import IntentDistribution
from app.release import ReleaseInvalidError, ReleaseInvalidReason
from app.suggestions.domain.analysis import (
    ConfidenceBand,
    IntentCandidate,
    ModelIntent,
    ReasonCode,
    Routing,
    RoutingRecommendation,
    StaffIntent,
)
from app.suggestions.domain.request import IntentName
from app.suggestions.domain.routing import RoutingConfiguration

# The 12 in-scope intents of the requirements (§3.2). `human_agent` is in scope, and never
# gets a draft (ESC-03).
IN_SCOPE_INTENTS = frozenset(
    IntentName(label)
    for label in (
        "track_order",
        "cancel_order",
        "delivery_time",
        "delivery_issue",
        "shipping_costs",
        "return_policy",
        "return_product",
        "refund_policy",
        "request_refund",
        "refund_status",
        "payment_issue",
        "human_agent",
    )
)
HUMAN_AGENT = IntentName("human_agent")
# The alternatives that an analysis shows, as the contract allows (`Analysis.alternatives`).
MAX_ALTERNATIVES = 4
# Every reason code that `ai-service` sets, in the order of the contract's `AiReasonCode`, so
# the codes of a result always come in the same order.
REASON_CODE_ORDER = tuple(
    ReasonCode(code)
    for code in (
        "low_confidence",
        "signal_disagreement",
        "out_of_scope_intent",
        "human_agent_requested",
        "requires_authority",
        "no_valid_document",
        "only_expired_documents",
        "conflicting_sources",
        "missing_information",
        "source_review_overdue",
        "grounding_failed",
        "llm_unavailable",
        "llm_invalid_output",
        "budget_exceeded",
    )
)
LOW_CONFIDENCE = ReasonCode("low_confidence")
OUT_OF_SCOPE_INTENT = ReasonCode("out_of_scope_intent")
HUMAN_AGENT_REQUESTED = ReasonCode("human_agent_requested")
REQUIRES_AUTHORITY = ReasonCode("requires_authority")
# The codes of routing that end in an abstention: no draft, manual handling (ESC-01, ESC-02,
# ESC-04).
ABSTENTION_CODES = frozenset(
    ReasonCode(code)
    for code in (
        "low_confidence",
        "out_of_scope_intent",
        "no_valid_document",
        "only_expired_documents",
        "conflicting_sources",
    )
)


@dataclass(frozen=True, slots=True)
class IntentAssessment:
    """The intent of a message, as routing reads it.

    Attributes:
        intent: The model's top intent with its band, or the intent that staff chose.
        alternatives: The next most likely intents of the model; none for a staff choice.
        low_confidence: Whether the model's intent fails τ or δ (ESC-01); never for a staff
            choice, which replaces the distribution (ADR-0005, statement 7).
    """

    intent: ModelIntent | StaffIntent
    alternatives: tuple[IntentCandidate, ...]
    low_confidence: bool


def assess_intent(
    distribution: IntentDistribution,
    override: IntentName | None,
    configuration: RoutingConfiguration,
) -> IntentAssessment:
    """Read the intent of a message from the model, or from the choice of staff.

    Args:
        distribution: The intent distribution of the model.
        override: The intent that staff chose or confirmed; None when none.
        configuration: The routing configuration of the release.

    Returns:
        The intent, its band, and whether its confidence is low.
    """
    if override is not None:
        return IntentAssessment(
            intent=StaffIntent(label=override), alternatives=(), low_confidence=False
        )
    top, *others = distribution.probabilities
    second = others[0].probability if others else 0.0
    low = (
        top.probability < configuration.min_top_probability
        or top.probability - second < configuration.min_top_two_gap
    )
    if low:
        band = ConfidenceBand.LOW
    elif top.probability >= configuration.high_band_min_probability:
        band = ConfidenceBand.HIGH
    else:
        band = ConfidenceBand.MEDIUM
    return IntentAssessment(
        intent=ModelIntent(IntentName(top.label), top.probability, band),
        alternatives=tuple(
            IntentCandidate(IntentName(entry.label), entry.probability)
            for entry in others[:MAX_ALTERNATIVES]
        ),
        low_confidence=low,
    )


def check_sensitive_intents(configuration: RoutingConfiguration, labels: frozenset[str]) -> None:
    """Refuse a routing configuration that names an intent that the model does not output.

    A sensitive intent outside the model's labels would always have probability 0, so the
    authority flag would never come from it without anyone knowing (FR-06).

    Args:
        configuration: The routing configuration of the release.
        labels: The intent labels of the model of the same release.

    Raises:
        ReleaseInvalidError: A sensitive intent is not a label of the model.
    """
    if not configuration.sensitive_intents <= labels:
        raise ReleaseInvalidError(ReleaseInvalidReason.ASSET_INVALID, asset="routing")


def requires_authority(
    message: str,
    distribution: IntentDistribution,
    override: IntentName | None,
    configuration: RoutingConfiguration,
) -> bool:
    """Tell whether a manager decides the request (FR-06, ESC-03).

    Two signals can only add the flag: a sensitive intent with a significant probability, even
    when it is not first, and a term of the sensitive-term list. A staff choice replaces the
    distribution. The LLM never sets the flag (contracts v1 design, Authority rule).

    Args:
        message: The pseudonymized message. Confidential.
        distribution: The intent distribution of the model.
        override: The intent that staff chose or confirmed; None when none.
        configuration: The routing configuration of the release.

    Returns:
        Whether authority is required.
    """
    if override is not None:
        sensitive = override in configuration.sensitive_intents
    else:
        sensitive = any(
            distribution.probability_of(label) >= configuration.sensitive_intent_min_probability
            for label in configuration.sensitive_intents
        )
    return sensitive or any(
        _holds_term(message, term.term) for term in configuration.sensitive_terms
    )


def route(
    intent: IntentAssessment,
    evidence_codes: frozenset[ReasonCode],
    *,
    authority_required: bool,
) -> Routing:
    """Recommend the next step for the ticket.

    `human_agent` leads to an escalation recommendation, which never sets the authority flag by
    itself (ESC-03b). A low confidence, an intent out of scope, or missing, expired, or
    conflicting evidence leads to an abstention (ESC-01, ESC-02, ESC-04). Otherwise the draft
    may be written; the authority flag never prevents it (ESC-03a).

    Args:
        intent: The intent of the message.
        evidence_codes: The reason codes of the evidence.
        authority_required: Whether a manager decides the request.

    Returns:
        The recommendation and its reason codes, in the order of the contract.
    """
    label = intent.intent.label
    codes = set(evidence_codes)
    if intent.low_confidence:
        codes.add(LOW_CONFIDENCE)
    if label not in IN_SCOPE_INTENTS:
        codes.add(OUT_OF_SCOPE_INTENT)
    if label == HUMAN_AGENT:
        codes.add(HUMAN_AGENT_REQUESTED)
    if authority_required:
        codes.add(REQUIRES_AUTHORITY)
    if HUMAN_AGENT_REQUESTED in codes:
        recommendation = RoutingRecommendation.ESCALATE
    elif codes & ABSTENTION_CODES:
        recommendation = RoutingRecommendation.ABSTAIN
    else:
        recommendation = RoutingRecommendation.DRAFT
    return Routing(recommendation=recommendation, reason_codes=ordered(codes))


def ordered(codes: set[ReasonCode] | frozenset[ReasonCode]) -> tuple[ReasonCode, ...]:
    """Put reason codes in the order of the contract, without repeats.

    Args:
        codes: The codes.

    Returns:
        The codes in the order of `AiReasonCode`.
    """
    return tuple(code for code in REASON_CODE_ORDER if code in codes)


def _holds_term(message: str, term: str) -> bool:
    # Whole words, any case, and any run of spaces between the words of the term.
    words = (re.escape(word) for word in term.split(" "))
    pattern = r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)"
    return re.search(pattern, message, re.IGNORECASE) is not None
