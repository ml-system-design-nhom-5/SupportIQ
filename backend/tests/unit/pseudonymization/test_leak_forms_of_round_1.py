"""The leak forms of round 1 of the backend comparison (leak fixes design, Unit tests).

One case per planted field that round 1 left whole or in part, from a `synthetic-dev-only` fixture
(DATA-03) rebuilt from the message set of that round. Each message runs through the detectors
that backend runs (`build_detectors`), with the known values of customer-1 and of the order that
it names. A case passes when the built text, which is what leaves backend, holds no word of the
planted value outside its placeholders, a lone title excepted, and the pre-send check lets that
text pass. The test takes the case ID, never the case, as its argument, and its assertions
compare counts and flags only, so a failure prints no message or value (LOG-29): pytest prints
the arguments of a failing test.
"""

import json
import re
from pathlib import Path
from typing import TypedDict

import pytest

from app.commerce import CustomerContact, OrderId, OrderReferences
from app.composition_root.suggestions_wiring import build_detectors
from app.pseudonymization.application import build_known_values
from app.pseudonymization.domain import (
    PLACEHOLDER_PATTERN,
    Detector,
    KnownValue,
    PersonalDataLeftError,
    PseudonymizedMessage,
    build_pseudonymized_message,
    check_nothing_left,
    drop_product_names,
    resolve_overlaps,
)

FIXTURE = Path(__file__).with_name("synthetic-dev-only-leak-forms-round-1-v1.json")
SEED = Path(__file__).parents[3] / "seed" / "synthetic-dev-only-v1.json"
CUSTOMER_LOGIN = "customer-1"
# The titles of the design (Layer 1, names, item 1): a title alone is no personal data.
TITLES = frozenset({"mr", "mrs", "ms", "miss", "dr", "ông", "bà", "chị", "cô", "chú"})
WORD = re.compile(r"\w+")


class LeakCase(TypedDict):
    """One planted field of round 1 that the detectors left whole or in part."""

    case: str
    message: str
    order_id: str
    field: str
    value: str


CASES: dict[str, LeakCase] = {
    case["case"]: case for case in json.loads(FIXTURE.read_text(encoding="utf-8"))["cases"]
}
SEED_DATA = json.loads(SEED.read_text(encoding="utf-8"))
PRODUCT_NAMES = tuple(product["name"] for product in SEED_DATA["commerce"]["products"])


@pytest.fixture(scope="module")
def detectors() -> tuple[Detector, ...]:
    return build_detectors()


def known_values(order_id: str) -> tuple[KnownValue, ...]:
    accounts, commerce = SEED_DATA["accounts"], SEED_DATA["commerce"]
    customer_id = next(a["customer_id"] for a in accounts if a["login_name"] == CUSTOMER_LOGIN)
    customer = next(c for c in commerce["customers"] if c["customer_id"] == customer_id)
    order = next(o for o in commerce["orders"] if o["order_id"] == order_id)
    contact = CustomerContact(
        display_name=customer["display_name"], email=customer["email"], phone=customer["phone"]
    )
    references = OrderReferences(
        order_id=OrderId(order_id),
        tracking_code=order["shipment"]["tracking_code"] if order["shipment"] else None,
        transaction_id=order["transaction_id"],
        shipping_address=order["shipping_address"],
    )
    return build_known_values(contact, references)


def pseudonymized(
    message: str, known: tuple[KnownValue, ...], detectors: tuple[Detector, ...]
) -> PseudonymizedMessage:
    # The detections that `PseudonymizeMessage` keeps, and the text that it builds from them.
    found = [detection for detector in detectors for detection in detector.detect(message, known)]
    kept = resolve_overlaps(drop_product_names(found, message, PRODUCT_NAMES))
    return build_pseudonymized_message(message, kept)


def words_left(text: str, value: str) -> int:
    """Count the words of the value, titles aside, that the text holds outside placeholders."""
    outside = {word.casefold() for word in WORD.findall(PLACEHOLDER_PATTERN.sub(" ", text))}
    return sum(
        1
        for word in WORD.findall(value)
        if word.casefold() not in TITLES and word.casefold() in outside
    )


def is_stopped(result: PseudonymizedMessage, known: tuple[KnownValue, ...]) -> bool:
    """Tell whether the pre-send check stops the built text."""
    try:
        check_nothing_left(result.text, result.entries, known)
    except PersonalDataLeftError:
        return True
    return False


@pytest.mark.parametrize("case_id", CASES)
def test_no_word_of_a_value_that_round_1_leaked_is_left(
    case_id: str, detectors: tuple[Detector, ...]
) -> None:
    case = CASES[case_id]
    known = known_values(case["order_id"])
    result = pseudonymized(case["message"], known, detectors)

    left = words_left(result.text, case["value"])

    assert left == 0, f"{case_id}: {left} word(s) of the {case['field']} left"
    assert not is_stopped(result, known), f"{case_id}: the pre-send check stops the text"
