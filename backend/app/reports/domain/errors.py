"""Errors of reports: the report period and the output file of the decision-record export.

The detail of `InvalidReportPeriodError` is the one of its contract example
`problems/invalid-period.json` (CON-06).
"""

from pathlib import Path
from typing import ClassVar

from app.platform import (
    BackendError,
    ErrorCode,
    InvalidRequestError,
    UnexpectedFailureError,
)

# The folder of the working directory that holds every export; it is git-ignored (SEC-33).
EXPORTS_FOLDER_NAME = "exports"


class InvalidReportPeriodError(InvalidRequestError):
    """`start_at` is not earlier than `end_at` (contract `InvalidReportPeriod`, 422)."""

    def __init__(self) -> None:
        """Build the error with the detail of its contract example."""
        super().__init__("The parameter start_at must be earlier than end_at.")


class ExportPathRefusedError(BackendError):
    """The output path of an export is not inside `exports/` of the working directory (SEC-33).

    The command stops before it reads or writes anything, and the detail names the path as the
    person gave it, so they can correct it.
    """

    code: ClassVar[ErrorCode] = ErrorCode.INVALID_REQUEST

    def __init__(self, output: Path) -> None:
        """Build the error from the refused path.

        Args:
            output: The output path, as given on the command line.
        """
        super().__init__(
            f"The output path {output} is not inside the folder {EXPORTS_FOLDER_NAME}/ of the"
            " working directory, so nothing was written."
        )


class ExportWriteFailedError(UnexpectedFailureError):
    """The export file could not be written, for example because the path is a folder."""
