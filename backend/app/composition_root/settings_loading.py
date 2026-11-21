"""Loading the settings at startup, and stopping with the names of invalid ones (ARCH-34)."""

from typing import ClassVar

from pydantic import ValidationError

from app.platform import BackendError, ErrorCode, EventName, EventRecorder
from app.platform.settings import Settings

_SETTING_CONTEXT_KEY = "setting"


class SettingsInvalidError(BackendError):
    """Startup stopped because settings are missing or invalid; the log names them."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, setting_names: tuple[str, ...]) -> None:
        """Keep the names of the settings, never their values.

        Args:
            setting_names: The names of the missing or invalid settings.
        """
        super().__init__("Settings are missing or invalid: " + ", ".join(setting_names))
        self.setting_names = setting_names


class SettingRequiredError(BackendError):
    """A command needs a setting that is optional for the `backend` replicas."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, setting_name: str) -> None:
        """Keep the name of the setting.

        Args:
            setting_name: The name of the missing setting.
        """
        super().__init__(f"The setting {setting_name} is required by this command")
        self.setting_name = setting_name


def load_settings(events: EventRecorder) -> Settings:
    """Read and validate every setting from the environment.

    Args:
        events: Where `settings.loaded` or `settings.invalid` is recorded.

    Returns:
        The validated settings.

    Raises:
        SettingsInvalidError: A setting is missing or invalid. The event names every such
            setting and never a value, because values can be secrets (PY-44).
    """
    try:
        # A settings class reads its values from the environment during validation; the empty
        # mapping adds none of its own.
        settings = Settings.model_validate({})
    except ValidationError as error:
        names = invalid_setting_names(error)
        events.record(EventName.SETTINGS_INVALID, setting_names=",".join(names))
        raise SettingsInvalidError(names) from error
    events.record(EventName.SETTINGS_LOADED)
    return settings


def require_setting[ValueT](value: ValueT | None, setting_name: str) -> ValueT:
    """Return a setting that one command needs, or stop.

    Args:
        value: The value of the setting.
        setting_name: The name of the setting, for the error.

    Returns:
        The value.

    Raises:
        SettingRequiredError: The setting is absent.
    """
    if value is None:
        raise SettingRequiredError(setting_name)
    return value


def invalid_setting_names(error: ValidationError) -> tuple[str, ...]:
    """Return the names of the settings that failed validation, without repeats.

    Args:
        error: The validation error of `Settings`.

    Returns:
        The setting names. Errors of a check across settings name the setting in their
        context.
    """
    names: list[str] = []
    for detail in error.errors(include_input=False, include_url=False):
        location = detail["loc"]
        context = detail.get("ctx", {})
        if location:
            names.append(str(location[0]))
        elif _SETTING_CONTEXT_KEY in context:
            names.append(str(context[_SETTING_CONTEXT_KEY]))
    return tuple(dict.fromkeys(names))
