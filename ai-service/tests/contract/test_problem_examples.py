"""The problem bodies of ai-service are those of their contract examples (CON-06, CON-12)."""

import json
from pathlib import Path

import pytest

from app.platform import (
    AiServiceError,
    ResourceNotFoundError,
    ServiceTokenRejectedError,
    TraceId,
    UnexpectedFailureError,
)
from app.platform.web import build_problem_response
from app.release import ReleaseNotLoadedError
from app.suggestions import UnknownKbVersionError

PROBLEM_EXAMPLES = Path(__file__).parents[3] / "contracts/examples/problems"


@pytest.mark.parametrize(
    ("example_name", "error"),
    [
        ("service-token-rejected", ServiceTokenRejectedError()),
        ("unknown-kb-version", UnknownKbVersionError()),
        ("not-found", ResourceNotFoundError()),
        ("release-not-loaded", ReleaseNotLoadedError()),
        ("internal-error", UnexpectedFailureError()),
    ],
)
def test_the_problem_of_an_error_is_its_contract_example(
    example_name: str, error: AiServiceError
) -> None:
    example = json.loads((PROBLEM_EXAMPLES / f"{example_name}.json").read_text(encoding="utf-8"))

    response = build_problem_response(error, TraceId(example["value"]["trace_id"]))

    assert json.loads(bytes(response.body)) == example["value"]
