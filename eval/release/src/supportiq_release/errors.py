"""The root error of the release command (PY-20), and the roots of the release download."""


class ReleaseCommandError(Exception):
    """The root of every error that the release command raises on purpose (PY-20).

    Each subclass names its problem with a stable code (ERR-02) and builds its message from
    codes, file names, and asset names only, never from text of the KB (LOG-29). The command
    line prints the message and exits with status 2.
    """


class DownloadDeclinedError(ReleaseCommandError):
    """The release download was not confirmed. The command line exits with status 4."""

    def __init__(self) -> None:
        """Build the error with a message that says how to confirm."""
        super().__init__(
            "The download is declined: answer y, or pass --yes when no terminal can answer."
        )


class NetworkFailedError(ReleaseCommandError):
    """A request to GitHub failed or was refused. The command line exits with status 5."""


class ReleaseCheckFailedError(ReleaseCommandError):
    """A release on GitHub, an archive, or a cached release fails a check. Exit status 6."""
