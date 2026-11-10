"""The setting of the handling mode names exactly the modes of the tickets feature."""

import pytest

from supportiq_backend.composition_root.tickets_wiring import to_handling_mode
from supportiq_backend.platform.settings import HandlingModeSetting
from supportiq_backend.tickets import HandlingMode


@pytest.mark.parametrize("setting", HandlingModeSetting)
def test_each_setting_maps_to_the_mode_with_its_value(setting: HandlingModeSetting) -> None:
    handling_mode = to_handling_mode(setting)

    assert handling_mode.value == setting.value


def test_every_handling_mode_has_a_setting() -> None:
    assert {mode.value for mode in HandlingMode} == {
        setting.value for setting in HandlingModeSetting
    }
