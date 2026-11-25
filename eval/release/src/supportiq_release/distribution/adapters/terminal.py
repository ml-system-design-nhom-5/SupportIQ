"""The one question of the release download: asked on standard error, answered on standard input.

Standard output holds only the path of the release folder, so the question and every message go
to standard error (release download and Modal deploy design, Download, Output). Only the answer
`y` goes on. Without a terminal on standard input, no question is asked at all. The streams are
read when a function runs, never when the module is imported.
"""

import sys

_YES = "y"


def can_answer() -> bool:
    """Tell whether a person can answer, that is, whether standard input is a terminal.

    Returns:
        True when standard input is a terminal.
    """
    return sys.stdin.isatty()


def confirms(question: str) -> bool:
    """Ask one question on standard error, and read one line of standard input.

    Args:
        question: The question, ending with `[y/N] `.

    Returns:
        True only when the line is exactly `y`.
    """
    sys.stderr.write(question)
    sys.stderr.flush()
    return sys.stdin.readline().rstrip("\n") == _YES
