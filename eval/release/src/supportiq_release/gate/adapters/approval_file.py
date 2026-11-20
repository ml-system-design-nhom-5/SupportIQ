"""Read the approval record next to a set of escalation cases, and check that it covers the set.

The record is `approval.json` in the folder of `cases.json`, in
`supportiq-case-set-approval/interim-1` (`data/benchmarks/escalation/interim-v1/README.md`, Approval
record). It is read strictly, like the set: a field that is missing, unknown, or of another type
refuses it. `run-gate` and `publish-candidate` both check it before they use the set.
"""

import re
from datetime import date
from pathlib import Path
from typing import cast

from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import read_json_file
from supportiq_release.gate.adapters.cases_file import CasesFile
from supportiq_release.gate.domain import (
    Approval,
    ApprovalProblem,
    ApprovalStatus,
    approval_problem,
)

APPROVAL_FILE_NAME = "approval.json"
APPROVAL_FORMAT = "supportiq-case-set-approval/interim-1"
_FIELDS = frozenset({"format", "set", "status", "cases_sha256", "approved_by", "approved_on"})
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")


class ApprovalInvalidError(ReleaseCommandError):
    """The approval record breaks its format."""

    def __init__(self) -> None:
        """Build the error with a message that names the file only."""
        super().__init__(f"The {APPROVAL_FILE_NAME} of the escalation cases breaks its format.")


class CasesNotApprovedError(ReleaseCommandError):
    """The approval record does not cover the set as it is. The message names the problem."""

    def __init__(self, problem: ApprovalProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the approval does not cover the set.
        """
        super().__init__(f"The escalation cases are not approved: {problem}.")
        self.problem = problem


def check_cases_approved(cases: CasesFile, cases_path: Path) -> Approval:
    """Read the approval record next to a set, and check that it covers the set as it is.

    Args:
        cases: The set, read from `cases_path`, with the SHA-256 of its file.
        cases_path: The file of the set; the record is in the same folder.

    Returns:
        The approval.

    Raises:
        JsonFileInvalidError: The record is missing, a link, unreadable, or not strict JSON.
        ApprovalInvalidError: The record breaks its format.
        CasesNotApprovedError: The record is of another set, is not frozen, or covers other
            bytes than those of the set as it is.
    """
    approval = read_approval(cases_path.parent / APPROVAL_FILE_NAME)
    problem = approval_problem(approval, cases.case_set.name, cases.sha256)
    if problem is not None:
        raise CasesNotApprovedError(problem)
    return approval


def read_approval(path: Path) -> Approval:
    """Read an approval record strictly.

    Args:
        path: The file, `approval.json`.

    Returns:
        The approval.

    Raises:
        JsonFileInvalidError: The file is missing, a link, unreadable, or not strict JSON.
        ApprovalInvalidError: The record breaks its format.
    """
    content = read_json_file(path).content
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    fields = cast("dict[str, object]", content) if isinstance(content, dict) else None
    if fields is None or frozenset(fields) != _FIELDS or fields["format"] != APPROVAL_FORMAT:
        raise ApprovalInvalidError
    status = fields["status"]
    if status not in set(ApprovalStatus):
        raise ApprovalInvalidError
    return Approval(
        case_set=_text(fields["set"]),
        status=ApprovalStatus(cast("str", status)),
        cases_sha256=_sha256(fields["cases_sha256"]),
        approved_by=None if fields["approved_by"] is None else _text(fields["approved_by"]),
        approved_on=None if fields["approved_on"] is None else _date(fields["approved_on"]),
    )


def _text(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApprovalInvalidError
    return value


def _sha256(value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ApprovalInvalidError
    return value


def _date(value: object) -> date:
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        raise ApprovalInvalidError
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ApprovalInvalidError from error
