"""The closed sets that the cases name are those of contract 1.0.0 of `ai-service` (CODE-30).

The domain of the gate keeps its own enums, because it imports no library and no `ai-service`.
These tests compare them with the models that `ai-service` generates from the contract, whose
freshness its CI checks (CON-26), so a change of the contract fails here.
"""

from supportiq_ai_service.generated import (
    AiServiceReasonCode,
    RoutingRecommendation,
    Status,
    Status1,
)

from supportiq_release.gate.domain import DraftStatus, ReasonCode, Recommendation


def test_the_recommendations_are_those_of_the_contract() -> None:
    assert {value.value for value in Recommendation} == {
        value.value for value in RoutingRecommendation
    }


def test_the_draft_statuses_are_those_of_the_contract() -> None:
    contract = {value.value for value in Status} | {value.value for value in Status1}

    assert {value.value for value in DraftStatus} == contract


def test_the_reason_codes_are_those_of_the_contract() -> None:
    assert {value.value for value in ReasonCode} == {value.value for value in AiServiceReasonCode}
