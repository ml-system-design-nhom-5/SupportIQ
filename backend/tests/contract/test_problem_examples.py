"""The problem bodies of backend are the ones of their contract examples (CON-06, ERR-15)."""

import json
from pathlib import Path

import pytest

from app.accounts import (
    AccountChangeRefusedError,
    AccountChangeRule,
    LoginNameTakenError,
)
from app.idempotency import IdempotencyKeyReusedError
from app.platform import BackendError, TraceId
from app.platform.web import build_problem_response

PROBLEM_EXAMPLES = Path(__file__).parents[3] / "contracts/examples/problems"
EXAMPLE_FILE = PROBLEM_EXAMPLES / "idempotency-key-reused.json"


def test_the_detail_of_a_reused_key_is_the_one_of_the_contract_example() -> None:
    example = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))

    assert IdempotencyKeyReusedError().detail == example["value"]["detail"]


@pytest.mark.parametrize(
    ("example_name", "error"),
    [
        ("login-name-taken", LoginNameTakenError()),
        (
            "admin-password-unresettable",
            AccountChangeRefusedError(AccountChangeRule.ADMIN_PASSWORD_UNRESETTABLE),
        ),
        (
            "current-password-incorrect",
            AccountChangeRefusedError(AccountChangeRule.CURRENT_PASSWORD_INCORRECT),
        ),
    ],
)
def test_the_problem_of_an_account_management_refusal_is_its_contract_example(
    example_name: str, error: BackendError
) -> None:
    example = json.loads((PROBLEM_EXAMPLES / f"{example_name}.json").read_text(encoding="utf-8"))

    response = build_problem_response(error, TraceId(example["value"]["trace_id"]))

    assert json.loads(bytes(response.body)) == example["value"]
