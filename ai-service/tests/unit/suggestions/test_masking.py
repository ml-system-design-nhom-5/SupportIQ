"""Personal-data patterns outside placeholders are masked before the LLM call (SEC-06)."""

import pytest

from app.suggestions.domain import MaskCounts
from app.suggestions.domain.masking import mask_personal_data, placeholders_in


@pytest.mark.parametrize(
    "email",
    [
        "an.example@example.com",
        "first+tag@mail.example.org",
        "A_B-C@sub.domain.co",
        "x@y.io",
        "oneil@example.net",
        "name.surname99@example-mail.com",
    ],
)
def test_an_email_address_is_masked(email: str) -> None:
    masked = mask_personal_data(f"Write to {email} please.")

    assert masked.text == "Write to [EMAIL] please."
    assert masked.counts == MaskCounts(email=1, phone=0, card=0)


@pytest.mark.parametrize(
    "card",
    [
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
        "5500 0000 0000 0004",
        "340000000000009",
        "6011000000000004",
    ],
)
def test_a_card_number_is_masked(card: str) -> None:
    masked = mask_personal_data(f"My card {card} was charged.")

    assert masked.text == "My card [CARD] was charged."
    assert masked.counts == MaskCounts(email=0, phone=0, card=1)


@pytest.mark.parametrize(
    "phone",
    [
        "+84 912 345 678",
        "0912345678",
        "(028) 3822 1234",
        "+1-202-555-0143",
        "202.555.0143",
        "+44 20 7946 0958",
    ],
)
def test_a_phone_number_is_masked(phone: str) -> None:
    masked = mask_personal_data(f"Call me at {phone} today.")

    assert masked.text == "Call me at [PHONE] today."
    assert masked.counts == MaskCounts(email=0, phone=1, card=0)


@pytest.mark.parametrize(
    "text",
    [
        "My order [ORDER_ID_1] is late.",
        "I paid $129.99 on 2026-11-05.",
        "It came on 05/11/2026 at 10:30.",
        "Version 1.2.3 of the app crashes.",
        "Order number 12345 and size 42.",
        "Card ending in 1111 was used.",
        "4111111111111112 is not a valid card number.",
        "Write to support at example dot com.",
        "Email me@localhost when you can.",
        "user@ alone, and @example.com alone.",
        "Write a@b when done.",
        "Write a@@b.com when done.",
        "Write a@b.c when done.",
        "Write @b.com when done.",
        "Call 12345 or 555-0143.",
        "[EMAIL] and [PHONE_2] stay as they are.",
    ],
)
def test_text_without_a_personal_data_pattern_is_kept(text: str) -> None:
    masked = mask_personal_data(text)

    assert masked.text == text
    assert masked.counts == MaskCounts(email=0, phone=0, card=0)


def test_placeholders_are_kept_and_counted_apart() -> None:
    masked = mask_personal_data(
        "[NAME_1] at [EMAIL_1], also a.b@example.com, phone 0912345678, card 4111111111111111."
    )

    assert masked.text == "[NAME_1] at [EMAIL_1], also [EMAIL], phone [PHONE], card [CARD]."
    assert masked.counts == MaskCounts(email=1, phone=1, card=1)
    assert placeholders_in(masked.text) == {"[NAME_1]", "[EMAIL_1]", "[EMAIL]", "[PHONE]", "[CARD]"}


@pytest.mark.parametrize(
    "text",
    [
        "Code 411111111111 has 12 digits.",
        "Code 41111111111111111111 has 20 digits.",
        "Card 4111 1111 1111 1112 fails the check.",
        "Card 4111-1111-1111-1112 fails the check.",
        "Card 4111111111111112 fails the check.",
        "Card ending in 1111 was used.",
    ],
)
def test_a_number_that_is_not_a_card_number_is_never_masked_as_a_card(text: str) -> None:
    masked = mask_personal_data(text)

    # A 12-digit code may still be masked as a phone number: masking more is the safe side.
    assert masked.counts.card == 0
    assert "[CARD]" not in masked.text


def test_two_phone_numbers_one_space_apart_are_both_masked() -> None:
    masked = mask_personal_data("My numbers 0912345678 0987654321")

    assert masked.text == "My numbers [PHONE] [PHONE]"
    assert masked.counts == MaskCounts(email=0, phone=2, card=0)
