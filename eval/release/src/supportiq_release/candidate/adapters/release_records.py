"""Keep a release ID from being used twice: one folder of records for each ID ever used.

A `release_id` is never reused, not even after a candidate fails the gate (ARCH-40). Each run
of the gate, passed or failed, keeps its record in `eval/releases/<release_id>/` (ADR-0021,
Release and the offline evaluation gate). A candidate gets a release ID only when no folder
of that name exists. The folder of records itself must exist, so a wrong path never lets an
ID through.
"""

from enum import StrEnum
from pathlib import Path

from supportiq_release.errors import ReleaseCommandError


class ReleaseIdProblem(StrEnum):
    """Why a release ID cannot be given to a candidate."""

    RECORDS_MISSING = "release_records_folder_missing"
    ALREADY_USED = "release_id_already_used"


class ReleaseIdNotFreeError(ReleaseCommandError):
    """A release ID cannot be given to a candidate."""

    def __init__(self, problem: ReleaseIdProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the ID cannot be given.
        """
        super().__init__(f"The release ID is refused: {problem}.")
        self.problem = problem


def check_release_id_free(records: Path, release_id: str) -> None:
    """Refuse a release ID that a record already holds.

    Args:
        records: The folder of the records of every release, such as `eval/releases/`.
        release_id: The ID of the new candidate.

    Raises:
        ReleaseIdNotFreeError: The folder of records is missing or not a folder, or a record
            of the ID exists.
    """
    if records.is_symlink() or not records.is_dir():
        raise ReleaseIdNotFreeError(ReleaseIdProblem.RECORDS_MISSING)
    record = records / release_id
    if record.is_symlink() or record.exists():
        raise ReleaseIdNotFreeError(ReleaseIdProblem.ALREADY_USED)
