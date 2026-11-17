"""Loading the settings at startup, and stopping with the names of invalid ones (ARCH-34)."""

from pathlib import Path
from typing import ClassVar

from pydantic import ValidationError

from supportiq_ai_service.platform import AiServiceError, ErrorCode, EventName, EventRecorder
from supportiq_ai_service.platform.settings import Settings

_SETTING_CONTEXT_KEY = "setting"


class SettingsInvalidError(AiServiceError):
    """Startup stopped because settings are missing or invalid; the log names them."""

    code: ClassVar[ErrorCode] = ErrorCode.INTERNAL_ERROR

    def __init__(self, setting_names: tuple[str, ...]) -> None:
        """Keep the names of the settings, never their values.

        Args:
            setting_names: The names of the missing or invalid settings.
        """
        super().__init__("Settings are missing or invalid: " + ", ".join(setting_names))
        self.setting_names = setting_names


def load_settings(events: EventRecorder, release_manifest_path: Path | None = None) -> Settings:
    """Read and validate every setting from the environment.

    Args:
        events: Where `settings.loaded` or `settings.invalid` is recorded.
        release_manifest_path: The release manifest, in place of `RELEASE_MANIFEST_PATH`. Only
            the offline evaluation gate passes one: the candidate that it runs.

    Returns:
        The validated settings.

    Raises:
        SettingsInvalidError: A setting is missing or invalid. The event names every such
            setting and never a value, because values can be secrets (PY-44).
    """
    given = (
        {} if release_manifest_path is None else {"release_manifest_path": release_manifest_path}
    )
    try:
        # A settings class reads its values from the environment during validation; a value
        # given here takes the place of its environment variable.
        settings = Settings.model_validate(given)
    except ValidationError as error:
        names = invalid_setting_names(error)
        events.record(EventName.SETTINGS_INVALID, setting_names=",".join(names))
        raise SettingsInvalidError(names) from error
    events.record(EventName.SETTINGS_LOADED)
    return settings


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
