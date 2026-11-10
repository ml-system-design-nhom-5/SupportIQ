"""Tests that `.env.example` lists every setting, and that its values are valid (ARCH-35)."""

import re
from pathlib import Path

from supportiq_backend.platform.settings import Settings
from tests.unit.platform.settings_builders import SettingsWithoutEnvironment

ENV_EXAMPLE = Path(__file__).parents[3] / ".env.example"
VARIABLE_PATTERN = re.compile(r"^#? ?([A-Z][A-Z0-9_]*)=", re.MULTILINE)
ACTIVE_LINE_PATTERN = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$", re.MULTILINE)
SINGLE_QUOTE = "'"


def active_values() -> dict[str, str]:
    lines = ACTIVE_LINE_PATTERN.findall(ENV_EXAMPLE.read_text(encoding="utf-8"))
    return {name.lower(): value.strip(SINGLE_QUOTE) for name, value in lines}


def test_env_example_lists_exactly_the_settings() -> None:
    listed = set(VARIABLE_PATTERN.findall(ENV_EXAMPLE.read_text(encoding="utf-8")))

    assert listed == {name.upper() for name in Settings.model_fields}


def test_values_of_env_example_are_valid_settings() -> None:
    settings = SettingsWithoutEnvironment.model_validate(active_values())

    assert settings.allowed_origins == ("http://localhost:5173",)


def test_every_value_with_double_quotes_is_in_single_quotes() -> None:
    lines = ACTIVE_LINE_PATTERN.findall(ENV_EXAMPLE.read_text(encoding="utf-8"))

    assert [
        name for name, value in lines if '"' in value and not value.startswith(SINGLE_QUOTE)
    ] == []
