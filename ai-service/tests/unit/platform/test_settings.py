"""Startup reads the settings from the environment and stops on invalid ones (ARCH-34)."""

from pathlib import Path

import pytest

from supportiq_ai_service.composition_root.settings_loading import (
    SettingsInvalidError,
    load_settings,
)
from supportiq_ai_service.platform import EventName
from tests.unit.platform.fakes import RecordingEventRecorder

SERVICE_TOKEN_VARIABLE = "SERVICE_TOKEN"
SERVICE_TOKEN = "service-token-for-unit-tests"
RELEASE_MANIFEST_PATH_VARIABLE = "RELEASE_MANIFEST_PATH"
RELEASE_MANIFEST_PATH = "/srv/release/release-manifest.json"


@pytest.fixture(autouse=True)
def release_manifest_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(RELEASE_MANIFEST_PATH_VARIABLE, RELEASE_MANIFEST_PATH)


def test_valid_settings_are_loaded_and_logged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    events = RecordingEventRecorder()

    settings = load_settings(events)

    assert settings.service_token.get_secret_value() == SERVICE_TOKEN
    assert settings.release_manifest_path == Path(RELEASE_MANIFEST_PATH)
    assert events.names() == (EventName.SETTINGS_LOADED,)


def test_a_missing_release_manifest_path_stops_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)
    monkeypatch.delenv(RELEASE_MANIFEST_PATH_VARIABLE)
    events = RecordingEventRecorder()

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(events)

    assert raised.value.setting_names == ("release_manifest_path",)
    (invalid,) = events.of(EventName.SETTINGS_INVALID)
    assert invalid.attributes == {"setting_names": "release_manifest_path"}


@pytest.mark.parametrize("value", [None, ""])
def test_a_missing_or_empty_service_token_stops_startup_without_its_value(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv(SERVICE_TOKEN_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, value)
    events = RecordingEventRecorder()

    with pytest.raises(SettingsInvalidError) as raised:
        load_settings(events)

    assert raised.value.setting_names == ("service_token",)
    (invalid,) = events.of(EventName.SETTINGS_INVALID)
    assert invalid.attributes == {"setting_names": "service_token"}


def test_the_service_token_never_appears_in_the_repr_of_the_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(SERVICE_TOKEN_VARIABLE, SERVICE_TOKEN)

    settings = load_settings(RecordingEventRecorder())

    assert SERVICE_TOKEN not in repr(settings)
