"""The logging of the `backend` process: redacted JSON lines on standard output (LOG-02)."""

import sys

from app.commerce import (
    ORDER_ID_PATTERN,
    PHONE_PATTERN,
    TRACKING_CODE_PATTERN,
    TRANSACTION_ID_PATTERN,
)
from app.platform import EventRecorder
from app.platform.adapters.logging_setup import (
    GENERIC_REDACTION_PATTERNS,
    Redactor,
    StandardLibraryEventRecorder,
    configure_logging,
)


def build_event_recorder() -> EventRecorder:
    """Send every log record of the process to standard output as JSON lines (LOG-02).

    Returns:
        The event recorder of the process.
    """
    return StandardLibraryEventRecorder(configure_logging(sys.stdout, build_redactor()))


def build_redactor() -> Redactor:
    """Combine the generic patterns with the documented ID formats of commerce (LOG-30).

    Returns:
        The redactor of every log line.
    """
    return Redactor(
        (
            *GENERIC_REDACTION_PATTERNS,
            ORDER_ID_PATTERN,
            TRACKING_CODE_PATTERN,
            TRANSACTION_ID_PATTERN,
            PHONE_PATTERN,
        )
    )
