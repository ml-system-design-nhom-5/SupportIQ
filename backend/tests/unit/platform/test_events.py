"""Tests of the event catalog: one name, level, and message per event (LOG-11, LOG-12, LOG-14)."""

import re

import pytest

from app.platform import EVENT_DESCRIPTIONS, EventName

EVENT_NAME_PATTERN = re.compile(r"[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*")
DESIGN_EVENTS = (
    "startup.completed",
    "settings.loaded",
    "settings.invalid",
    "shutdown.started",
    "ticket.created",
    "account.role_changed",
    "account.status_changed",
    "permission.denied",
)


def test_every_event_has_exactly_one_description() -> None:
    described = set(EVENT_DESCRIPTIONS)

    assert described == set(EventName)


@pytest.mark.parametrize("event_name", DESIGN_EVENTS)
def test_catalog_holds_every_event_of_the_design(event_name: str) -> None:
    event = EventName(event_name)

    assert event in EVENT_DESCRIPTIONS


@pytest.mark.parametrize("event", list(EventName))
def test_event_name_is_an_area_and_a_past_tense_verb(event: EventName) -> None:
    is_valid_name = EVENT_NAME_PATTERN.fullmatch(event.value) is not None

    assert is_valid_name


@pytest.mark.parametrize("event", list(EventName))
def test_event_message_is_one_sentence_without_trailing_period(event: EventName) -> None:
    message = EVENT_DESCRIPTIONS[event].message

    assert message[0].isupper()
    assert not message.endswith(".")
