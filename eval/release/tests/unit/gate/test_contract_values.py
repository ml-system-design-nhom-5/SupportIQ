"""The closed sets that the cases name are those of contract 1.0.0 of `ai-service` (CODE-30).

The domain of the gate keeps its own enums, because it imports no library and no `ai-service`.
These tests compare them with the models that `ai-service` generates from the contract, whose
freshness its CI checks (CON-26), so a change of the contract fails here.
"""

import json
import re
from pathlib import Path

from app.generated import (
    AiServiceReasonCode,
    RoutingRecommendation,
    Status,
    Status1,
    Type,
)

from supportiq_release.gate.domain import DraftStatus, ProblemType, ReasonCode, Recommendation

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
CONTRACTS = REPOSITORY_ROOT / "contracts"


def _problem_types_of_the_ai_service_contract() -> set[str]:
    # The `type` of each Problem Details example that the contract of `ai-service` refers to.
    contract = (CONTRACTS / "ai-service.openapi.yaml").read_text()
    examples = set(re.findall(r"examples/problems/([a-z-]+\.json)", contract))
    return {
        json.loads((CONTRACTS / "examples" / "problems" / name).read_text())["value"]["type"]
        for name in examples
    }


def test_the_problem_types_are_those_that_the_ai_service_contract_gives() -> None:
    problem_types = {value.value for value in ProblemType}

    assert problem_types == _problem_types_of_the_ai_service_contract()
    assert problem_types <= {value.value for value in Type}


def test_the_recommendations_are_those_of_the_contract() -> None:
    assert {value.value for value in Recommendation} == {
        value.value for value in RoutingRecommendation
    }


def test_the_draft_statuses_are_those_of_the_contract() -> None:
    contract = {value.value for value in Status} | {value.value for value in Status1}

    assert {value.value for value in DraftStatus} == contract


def test_the_reason_codes_are_those_of_the_contract() -> None:
    assert {value.value for value in ReasonCode} == {value.value for value in AiServiceReasonCode}
