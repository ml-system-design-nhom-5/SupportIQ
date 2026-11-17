"""The approval of a set of escalation cases by the project lead (ADR-0021, Exception to TEST-26).

The gate and publishing use a set only when its approval is frozen, names who approved it and
when, and covers exactly the bytes of its file as they are. A set that changed after its
approval is not the approved set, so it needs a new approval (DATA-25).
"""

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class ApprovalStatus(StrEnum):
    """Whether the project lead has approved the set."""

    DRAFT = "draft"
    FROZEN = "frozen"


class ApprovalProblem(StrEnum):
    """Why the approval of a set does not let the gate or publishing use it."""

    OTHER_SET = "approval_of_another_set"
    NOT_FROZEN = "cases_not_frozen"
    CASES_CHANGED = "cases_not_those_of_the_approval"


@dataclass(frozen=True, slots=True)
class Approval:
    """The approval record of one set.

    Attributes:
        case_set: The name of the set that the approval is for.
        status: Draft until the project lead approves the set, then frozen.
        cases_sha256: The SHA-256 of the file of the cases that the approval covers.
        approved_by: Who approved the set, or None while it is a draft.
        approved_on: The date of the approval, or None while it is a draft.
    """

    case_set: str
    status: ApprovalStatus
    cases_sha256: str
    approved_by: str | None
    approved_on: date | None


def approval_problem(
    approval: Approval, case_set: str, cases_sha256: str
) -> ApprovalProblem | None:
    """Return why an approval does not cover a set as it is, or None when it does.

    Args:
        approval: The approval record next to the set.
        case_set: The name of the set.
        cases_sha256: The SHA-256 of the file of the set as it is now.

    Returns:
        The problem, or None when the set is approved, frozen, and unchanged.
    """
    if approval.case_set != case_set:
        return ApprovalProblem.OTHER_SET
    if (
        approval.status is not ApprovalStatus.FROZEN
        or approval.approved_by is None
        or approval.approved_on is None
    ):
        return ApprovalProblem.NOT_FROZEN
    if approval.cases_sha256 != cases_sha256:
        return ApprovalProblem.CASES_CHANGED
    return None
