"""Tests of reading a text that an adapter stored from an enum (PY-20, ERR-05)."""

from enum import StrEnum

import pytest

from app.platform import UnexpectedFailureError
from app.platform.persistence import parse_optional_stored_enum, parse_stored_enum


class StoredState(StrEnum):
    """The values of a column of these tests."""

    OPEN = "open"
    CLOSED = "closed"


@pytest.mark.parametrize("state", list(StoredState))
def test_parse_stored_enum_returns_the_member_of_each_value(state: StoredState) -> None:
    assert parse_stored_enum(StoredState, state.value) is state


# A value that no member has, the name of a member in place of its value, and empty text.
@pytest.mark.parametrize("value", ["archived", "OPEN", ""])
def test_parse_stored_enum_of_a_value_that_no_member_has_is_an_unexpected_failure(
    value: str,
) -> None:
    with pytest.raises(UnexpectedFailureError) as caught:
        parse_stored_enum(StoredState, value)

    assert isinstance(caught.value.__cause__, ValueError)


def test_parse_optional_stored_enum_of_none_is_none() -> None:
    assert parse_optional_stored_enum(StoredState, None) is None


def test_parse_optional_stored_enum_returns_the_member_of_a_value() -> None:
    assert parse_optional_stored_enum(StoredState, "closed") is StoredState.CLOSED


def test_parse_optional_stored_enum_of_a_value_that_no_member_has_is_an_unexpected_failure() -> (
    None
):
    with pytest.raises(UnexpectedFailureError) as caught:
        parse_optional_stored_enum(StoredState, "archived")

    assert isinstance(caught.value.__cause__, ValueError)
