"""The settings of the release download, read once from the environment (PY-43).

- `SUPPORTIQ_RELEASE_TOKEN`: the token sent to `api.github.com`, optional. Empty counts as not
  set. Secret (PY-44): it is never printed or written (ADR-0030, Download, statement 2).
- `SUPPORTIQ_RELEASE_CACHE`: the cache folder, an absolute path. Empty counts as not set, and
  the default is `$HOME/.cache/supportiq/releases`, without `XDG_CACHE_HOME`, so the bash of the
  local run computes the same path. In a container, the caller always sets it to the path on the
  host (release download and Modal deploy design, Download, In a container).

A setting that breaks its rule stops the command with status 2 and a message that names it,
never its value, as `ai-service` does with its settings.
"""

from pathlib import Path

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from supportiq_release.errors import ReleaseCommandError

TOKEN_SETTING = "SUPPORTIQ_RELEASE_TOKEN"  # noqa: S105  # the name of the variable, not a token
CACHE_SETTING = "SUPPORTIQ_RELEASE_CACHE"
HOME_SETTING = "HOME"
_CACHE_BELOW_HOME = (".cache", "supportiq", "releases")


class DownloadSettingsInvalidError(ReleaseCommandError):
    """A setting of the release download breaks its rule. The message names it, never its value."""

    def __init__(self, names: tuple[str, ...]) -> None:
        """Build the error with a message that names the settings.

        Args:
            names: The environment names of the settings that break their rule.
        """
        super().__init__(
            f"The settings of the release download are refused: {', '.join(names)}."
            f" {CACHE_SETTING} must be an absolute path, and {HOME_SETTING} must be an absolute"
            " path when the cache is not set."
        )
        self.names = names


class DownloadSettings(BaseSettings):
    """The settings of the release download.

    Attributes:
        release_token: The token of `SUPPORTIQ_RELEASE_TOKEN`, or None.
        release_cache: The cache folder of `SUPPORTIQ_RELEASE_CACHE`, or None for the default.
        home: The home folder of `HOME`, read only for the default cache folder, so a command
            that needs no cache, such as `check-pinned-release`, never depends on it.
    """

    model_config = SettingsConfigDict(case_sensitive=True, extra="ignore", frozen=True)

    release_token: SecretStr | None = Field(default=None, alias=TOKEN_SETTING)
    release_cache: Path | None = Field(default=None, alias=CACHE_SETTING)
    home: Path | None = Field(default=None, alias=HOME_SETTING)

    @field_validator("release_token", "release_cache", "home", mode="before")
    @classmethod
    def _empty_is_not_set(cls, value: object) -> object:
        return None if value == "" else value

    def cache_folder(self) -> Path:
        """Return the cache folder: the setting, or the default below the home folder.

        Both are checked only here, so a command that needs no cache, such as
        `check-pinned-release`, never depends on them.

        Returns:
            An absolute path.

        Raises:
            DownloadSettingsInvalidError: The cache is set but not absolute, which an unexpanded
                `~` is too; or it is not set, and the home folder is not set or not absolute.
        """
        if self.release_cache is not None:
            if not self.release_cache.is_absolute():
                raise DownloadSettingsInvalidError((CACHE_SETTING,))
            return self.release_cache
        if self.home is None or not self.home.is_absolute():
            raise DownloadSettingsInvalidError((CACHE_SETTING, HOME_SETTING))
        return self.home.joinpath(*_CACHE_BELOW_HOME)


def load_download_settings() -> DownloadSettings:
    """Read the settings of the release download from the environment.

    Returns:
        The settings.

    Raises:
        DownloadSettingsInvalidError: A setting breaks its rule. The message names the setting;
            only the cause, which the command never prints, holds the value.
    """
    try:
        return DownloadSettings()
    except ValidationError as error:
        names = tuple(
            dict.fromkeys(
                str(issue["loc"][0])
                for issue in error.errors(include_input=False, include_url=False)
                if issue["loc"]
            )
        )
        raise DownloadSettingsInvalidError(names) from error
