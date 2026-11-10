"""The detail of a reused key is the one of its contract example (CON-06, ERR-15)."""

import json
from pathlib import Path

from supportiq_backend.idempotency import IdempotencyKeyReusedError

EXAMPLE_FILE = Path(__file__).parents[3] / "contracts/examples/problems/idempotency-key-reused.json"


def test_the_detail_of_a_reused_key_is_the_one_of_the_contract_example() -> None:
    example = json.loads(EXAMPLE_FILE.read_text(encoding="utf-8"))

    assert IdempotencyKeyReusedError().detail == example["value"]["detail"]
