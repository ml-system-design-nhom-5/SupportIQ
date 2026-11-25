"""The approval of a set: only a frozen approval of the bytes as they are lets the gate use it."""

import hashlib
import json
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from supportiq_release.files import JsonFileInvalidError
from supportiq_release.gate.adapters import (
    ApprovalInvalidError,
    CasesNotApprovedError,
    check_cases_approved,
    read_approval,
    read_cases_file,
)
from supportiq_release.gate.domain import (
    Approval,
    ApprovalProblem,
    ApprovalStatus,
    approval_problem,
)
from tests.unit.gate.fakes import SET_NAME, approval_document, write_set

REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
REPOSITORY_SET = REPOSITORY_ROOT / "data" / "benchmarks" / "escalation" / "interim-v1"
SHA256 = "a" * 64
FROZEN = Approval(
    case_set=SET_NAME,
    status=ApprovalStatus.FROZEN,
    cases_sha256=SHA256,
    approved_by="project lead",
    approved_on=date(2026, 11, 17),
)


def _approval(**fields: object) -> Approval:
    return replace(FROZEN, **fields)


def test_a_frozen_approval_of_the_same_bytes_covers_the_set() -> None:
    assert approval_problem(_approval(), SET_NAME, SHA256) is None


@pytest.mark.parametrize(
    ("fields", "problem"),
    [
        ({"status": ApprovalStatus.DRAFT}, ApprovalProblem.NOT_FROZEN),
        ({"approved_by": None}, ApprovalProblem.NOT_FROZEN),
        ({"approved_on": None}, ApprovalProblem.NOT_FROZEN),
        ({"cases_sha256": "b" * 64}, ApprovalProblem.CASES_CHANGED),
        ({"case_set": "escalation/other-v1"}, ApprovalProblem.OTHER_SET),
    ],
)
def test_an_approval_that_does_not_cover_the_set_names_why(
    fields: dict[str, object], problem: ApprovalProblem
) -> None:
    assert approval_problem(_approval(**fields), SET_NAME, SHA256) is problem


def test_a_draft_of_other_bytes_is_refused_as_not_frozen_first() -> None:
    approval = _approval(status=ApprovalStatus.DRAFT, cases_sha256="b" * 64)

    assert approval_problem(approval, SET_NAME, SHA256) is ApprovalProblem.NOT_FROZEN


def test_the_repository_set_is_frozen_for_its_bytes() -> None:
    cases_path = REPOSITORY_SET / "cases.json"

    approval = check_cases_approved(read_cases_file(cases_path), cases_path)

    assert approval.status is ApprovalStatus.FROZEN
    assert approval.cases_sha256 == hashlib.sha256(cases_path.read_bytes()).hexdigest()
    assert approval.approved_on == date(2026, 11, 17)


def test_a_frozen_set_is_approved(tmp_path: Path) -> None:
    cases_path = write_set(tmp_path / "set")

    approval = check_cases_approved(read_cases_file(cases_path), cases_path)

    assert approval == replace(FROZEN, cases_sha256=read_cases_file(cases_path).sha256)


def test_a_draft_set_is_refused(tmp_path: Path) -> None:
    cases_path = write_set(
        tmp_path / "set", approval={"status": "draft", "approved_by": None, "approved_on": None}
    )

    with pytest.raises(CasesNotApprovedError) as refused:
        check_cases_approved(read_cases_file(cases_path), cases_path)

    assert refused.value.problem is ApprovalProblem.NOT_FROZEN
    assert str(refused.value) == "The escalation cases are not approved: cases_not_frozen."


def test_a_set_changed_after_its_approval_is_refused(tmp_path: Path) -> None:
    cases_path = write_set(tmp_path / "set")
    cases_path.write_bytes(cases_path.read_bytes() + b"\n")

    with pytest.raises(CasesNotApprovedError) as refused:
        check_cases_approved(read_cases_file(cases_path), cases_path)

    assert refused.value.problem is ApprovalProblem.CASES_CHANGED


def test_a_set_without_an_approval_record_is_refused(tmp_path: Path) -> None:
    cases_path = write_set(tmp_path / "set")
    (cases_path.parent / "approval.json").unlink()

    with pytest.raises(JsonFileInvalidError):
        check_cases_approved(read_cases_file(cases_path), cases_path)


@pytest.mark.parametrize(
    "fields",
    [
        {"format": "supportiq-case-set-approval/interim-2"},
        {"status": "approved"},
        {"status": None},
        {"set": ""},
        {"set": 1},
        {"cases_sha256": "A" * 64},
        {"cases_sha256": "a" * 63},
        {"approved_by": " "},
        {"approved_by": 1},
        {"approved_on": "17/11/2026"},
        {"approved_on": "20261117"},
        {"approved_on": "2026-02-30"},
        {"approved_on": 20261117},
        {"extra": True},
    ],
)
def test_an_approval_that_breaks_its_format_is_refused(
    tmp_path: Path, fields: dict[str, object]
) -> None:
    path = tmp_path / "approval.json"
    path.write_text(json.dumps({**approval_document(SHA256), **fields}))

    with pytest.raises(ApprovalInvalidError) as refused:
        read_approval(path)

    assert str(refused.value) == "The approval.json of the escalation cases breaks its format."


@pytest.mark.parametrize("missing", ["format", "set", "approved_by", "approved_on"])
def test_an_approval_without_a_field_is_refused(tmp_path: Path, missing: str) -> None:
    document = approval_document(SHA256)
    del document[missing]
    path = tmp_path / "approval.json"
    path.write_text(json.dumps(document))

    with pytest.raises(ApprovalInvalidError):
        read_approval(path)


def test_an_approval_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "approval.json"
    path.write_text("[]")

    with pytest.raises(ApprovalInvalidError):
        read_approval(path)
