"""Tests of the event catalog: one name, level, and message per event (LOG-11, LOG-12, LOG-14)."""

import re

import pytest

from supportiq_ai_service.platform import EVENT_DESCRIPTIONS, EventLevel, EventName

EVENT_NAME_PATTERN = re.compile(r"[a-z]+(_[a-z]+)*\.[a-z]+(_[a-z]+)*")
# The events of LOG-19 for `ai-service` and for both components.
REQUIRED_EVENTS = (
    "startup.completed",
    "settings.loaded",
    "settings.invalid",
    "shutdown.started",
    "release.loaded",
    "model.loaded",
    "kb.loaded",
    "analysis.completed",
    "draft.generated",
    "draft.abstained",
    "escalation.recommended",
    "personal_data.masked",
    "llm.call_failed",
    "grounding.check_failed",
)


def test_every_event_has_exactly_one_description() -> None:
    described = set(EVENT_DESCRIPTIONS)

    assert described == set(EventName)


@pytest.mark.parametrize("event_name", REQUIRED_EVENTS)
def test_catalog_holds_every_required_event(event_name: str) -> None:
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


@pytest.mark.parametrize(
    ("event", "level"),
    [
        # Abstention and escalation are correct behavior, not failures (LOG-16).
        (EventName.DRAFT_ABSTAINED, EventLevel.INFO),
        (EventName.ESCALATION_RECOMMENDED, EventLevel.INFO),
        # A failed draft step is degraded but handled: no draft, and staff may retry (LOG-15).
        (EventName.LLM_CALL_FAILED, EventLevel.WARNING),
        (EventName.GROUNDING_CHECK_FAILED, EventLevel.WARNING),
    ],
)
def test_an_outcome_of_a_draft_has_the_level_of_its_meaning(
    event: EventName, level: EventLevel
) -> None:
    assert EVENT_DESCRIPTIONS[event].level is level
