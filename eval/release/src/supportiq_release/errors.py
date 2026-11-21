"""The root error of the release command (PY-20)."""


class ReleaseCommandError(Exception):
    """The root of every error that the release command raises on purpose (PY-20).

    Each subclass names its problem with a stable code (ERR-02) and builds its message from
    codes, file names, and asset names only, never from text of the KB (LOG-29). The command
    line prints the message and exits with status 2.
    """
