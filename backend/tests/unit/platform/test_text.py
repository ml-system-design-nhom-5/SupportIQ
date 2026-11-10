"""Tests of what the database can store in a text column."""

import pytest

from supportiq_backend.platform import is_storable_text


@pytest.mark.parametrize("text", ["", "plain", "Đèn bàn", "emoji \U0001f600", "tab\tand\nnewline"])
def test_text_without_a_nul_or_a_lone_surrogate_is_storable(text: str) -> None:
    assert is_storable_text(text) is True


@pytest.mark.parametrize("text", ["\x00", "a\x00b", "\ud800", "before\udfffafter"])
def test_nul_and_lone_surrogates_are_not_storable(text: str) -> None:
    assert is_storable_text(text) is False
