"""One routing turns the intent, the evidence, and the authority flag into a recommendation."""

import dataclasses

import pytest

from app.intent import INTENT_LABELS
from app.release.manifest import ReleaseInvalidError
from app.suggestions.domain import (
    AuthorityCategory,
    ConfidenceBand,
    IntentName,
    ModelIntent,
    ReasonCode,
    RoutingConfiguration,
    RoutingRecommendation,
    SensitiveTerm,
    StaffIntent,
)
from app.suggestions.domain.routing_rules import (
    IN_SCOPE_INTENTS,
    IntentAssessment,
    assess_intent,
    check_sensitive_intents,
    requires_authority,
    route,
)
from tests.unit.intent.fakes import distribution

CONFIGURATION = RoutingConfiguration(
    version="routing-sample-1",
    model_version="intent-model-sample-1",
    min_top_probability=0.5,
    min_top_two_gap=0.1,
    rerank_weight=0.2,
    high_band_min_probability=0.9,
    sensitive_intents=frozenset({IntentName("request_refund")}),
    sensitive_intent_min_probability=0.2,
    sensitive_terms=(
        SensitiveTerm("lawyer", AuthorityCategory.LEGAL_CLAIM),
        SensitiveTerm("stolen card", AuthorityCategory.SUSPECTED_FRAUD),
    ),
)
TRACK_ORDER = IntentName("track_order")
# The in-scope intents of the requirements (§3.2).
IN_SCOPE_COUNT = 12


def _assessed(*entries: tuple[str, float]) -> IntentAssessment:
    return assess_intent(distribution(*entries), None, CONFIGURATION)


def test_the_in_scope_intents_are_the_12_of_the_requirements() -> None:
    assert len(IN_SCOPE_INTENTS) == IN_SCOPE_COUNT
    assert IN_SCOPE_INTENTS.issubset(INTENT_LABELS)


@pytest.mark.parametrize(
    ("entries", "band", "low"),
    [
        ((("track_order", 0.95), ("delivery_time", 0.05)), ConfidenceBand.HIGH, False),
        ((("track_order", 0.9), ("delivery_time", 0.1)), ConfidenceBand.HIGH, False),
        ((("track_order", 0.7), ("delivery_time", 0.3)), ConfidenceBand.MEDIUM, False),
        ((("track_order", 0.5), ("delivery_time", 0.3)), ConfidenceBand.MEDIUM, False),
        ((("track_order", 0.49), ("delivery_time", 0.3)), ConfidenceBand.LOW, True),
        ((("track_order", 0.55), ("delivery_time", 0.46)), ConfidenceBand.LOW, True),
    ],
)
def test_the_band_and_low_confidence_follow_tau_delta_and_the_high_band(
    entries: tuple[tuple[str, float], ...], band: ConfidenceBand, *, low: bool
) -> None:
    assessed = _assessed(*entries)

    assert assessed.intent == ModelIntent(TRACK_ORDER, entries[0][1], band)
    assert assessed.low_confidence is low


def test_the_alternatives_are_the_next_four_intents_of_the_model() -> None:
    assessed = _assessed(("track_order", 0.6), ("delivery_time", 0.2), ("delivery_issue", 0.1))

    assert [alternative.label for alternative in assessed.alternatives][:2] == [
        "delivery_time",
        "delivery_issue",
    ]
    assert len(assessed.alternatives) == 4  # noqa: PLR2004  # contract `Analysis.alternatives`


def test_a_staff_choice_has_no_probability_no_alternatives_and_never_a_low_confidence() -> None:
    assessed = assess_intent(
        distribution(("track_order", 0.3), ("delivery_time", 0.29)),
        IntentName("request_refund"),
        CONFIGURATION,
    )

    assert assessed == IntentAssessment(
        intent=StaffIntent(IntentName("request_refund")), alternatives=(), low_confidence=False
    )


@pytest.mark.parametrize(
    ("entries", "message", "required"),
    [
        ((("track_order", 0.7), ("request_refund", 0.2)), "Where is it?", True),
        ((("track_order", 0.81), ("request_refund", 0.19)), "Where is it?", False),
        ((("request_refund", 0.9),), "My money back please.", True),
        ((("track_order", 0.9),), "My LAWYER will call.", True),
        ((("track_order", 0.9),), "Someone used my stolen\n card.", True),
        ((("track_order", 0.9),), "The lawyers' office is near.", False),
        ((("track_order", 0.9),), "A stolen cardigan.", False),
    ],
)
def test_a_sensitive_intent_or_a_sensitive_term_requires_authority(
    entries: tuple[tuple[str, float], ...], message: str, *, required: bool
) -> None:
    assert requires_authority(message, distribution(*entries), None, CONFIGURATION) is required


def test_a_sensitive_staff_choice_requires_authority_and_replaces_the_distribution() -> None:
    model = distribution(("track_order", 0.5), ("request_refund", 0.5))

    assert requires_authority("Hello", model, IntentName("request_refund"), CONFIGURATION)
    assert not requires_authority("Hello", model, TRACK_ORDER, CONFIGURATION)


def test_a_sensitive_intent_that_the_model_never_outputs_is_refused_at_load() -> None:
    configuration = dataclasses.replace(
        CONFIGURATION, sensitive_intents=frozenset({IntentName("refund_now")})
    )

    with pytest.raises(ReleaseInvalidError):
        check_sensitive_intents(configuration, frozenset(INTENT_LABELS))
    check_sensitive_intents(CONFIGURATION, frozenset(INTENT_LABELS))


def _codes(*codes: str) -> frozenset[ReasonCode]:
    return frozenset(ReasonCode(code) for code in codes)


def test_human_agent_is_escalated_without_the_authority_flag_and_without_a_draft() -> None:
    routing = route(
        _assessed(("human_agent", 0.95)), _codes("no_valid_document"), authority_required=False
    )

    assert routing.recommendation is RoutingRecommendation.ESCALATE
    assert routing.reason_codes == _ordered("human_agent_requested", "no_valid_document")


def test_a_sensitive_term_adds_the_authority_flag_to_human_agent_too() -> None:
    routing = route(_assessed(("human_agent", 0.95)), _codes(), authority_required=True)

    assert routing.recommendation is RoutingRecommendation.ESCALATE
    assert routing.reason_codes == _ordered("human_agent_requested", "requires_authority")


@pytest.mark.parametrize(
    ("assessed", "evidence", "codes"),
    [
        (_assessed(("track_order", 0.4), ("delivery_time", 0.3)), (), ("low_confidence",)),
        (_assessed(("store_location", 0.95)), (), ("out_of_scope_intent",)),
        (_assessed(("track_order", 0.95)), ("no_valid_document",), ("no_valid_document",)),
        (
            _assessed(("track_order", 0.95)),
            ("only_expired_documents",),
            ("only_expired_documents",),
        ),
        (_assessed(("track_order", 0.95)), ("conflicting_sources",), ("conflicting_sources",)),
    ],
)
def test_low_confidence_out_of_scope_or_missing_evidence_abstains(
    assessed: IntentAssessment, evidence: tuple[str, ...], codes: tuple[str, ...]
) -> None:
    routing = route(assessed, _codes(*evidence), authority_required=False)

    assert routing.recommendation is RoutingRecommendation.ABSTAIN
    assert routing.reason_codes == _ordered(*codes)


def test_a_confident_in_scope_intent_with_evidence_may_be_drafted_even_with_authority() -> None:
    routing = route(_assessed(("request_refund", 0.95)), _codes(), authority_required=True)

    assert routing.recommendation is RoutingRecommendation.DRAFT
    assert routing.reason_codes == _ordered("requires_authority")


def test_reason_codes_come_in_the_order_of_the_contract() -> None:
    routing = route(
        _assessed(("store_location", 0.4), ("track_order", 0.39)),
        _codes("conflicting_sources"),
        authority_required=True,
    )

    assert routing.reason_codes == _ordered(
        "low_confidence", "out_of_scope_intent", "requires_authority", "conflicting_sources"
    )


def _ordered(*codes: str) -> tuple[ReasonCode, ...]:
    return tuple(ReasonCode(code) for code in codes)


def test_a_gap_of_exactly_delta_is_not_a_low_confidence() -> None:
    # Values exact in binary, so the gap is exactly δ.
    configuration = dataclasses.replace(CONFIGURATION, min_top_two_gap=0.25)

    assessed = assess_intent(
        distribution(("track_order", 0.75), ("delivery_time", 0.5)), None, configuration
    )

    assert assessed.low_confidence is False
