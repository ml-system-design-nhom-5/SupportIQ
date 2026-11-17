"""Write the record of one gate run into the folder of records of its release ID, and read it.

Each run, passed or failed, keeps its record in `eval/releases/<release_id>/gate-run.json`, so
an ID that a gate run used is never given again (ARCH-40, ADR-0021, Release and the offline
evaluation gate). The folder is created exclusively: a second run with the same ID is refused,
and so is a candidate built with an ID that a run already used.

The record holds identifiers, versions, checksums, counts, and codes, never text of a message
or of the KB (LOG-29). It states every part, what each case rests on, which parts load the
candidate, the test classes of each folder of guardrail tests, that no LLM call was made, and
the known gaps of the first release (ADR-0021, statement 4; ADR-0025). This module alone knows
the fields of the format: `publish-candidate` reads a record with `read_gate_record`.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from supportiq_release.candidate.adapters import (
    ReleaseIdNotFreeError,
    ReleaseIdProblem,
    check_release_id_free,
)
from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import read_json_file, write_json_file
from supportiq_release.gate.domain import (
    CANDIDATE_SCOPE,
    KNOWN_GAPS,
    NO_LLM_CALL,
    SHARED_SCENARIO_SET_ITEM,
    CaseResult,
    CheckResult,
    GateOutcome,
    GuardrailResult,
    GuardrailSuite,
)

RECORD_FORMAT = "supportiq-gate-run/interim-1"
RECORD_FILE_NAME = "gate-run.json"
PASSED = "passed"
FAILED = "failed"
LLM_CALLED = (
    "The LLM step of the gate received a call, so the gate fails (ADR-0021, CI, statement 2)."
)
# The fields of the format that the reader reads too.
_FORMAT = "format"
_RUN_ID = "run_id"
_RELEASE_ID = "release_id"
_MANIFEST_SHA256 = "manifest_sha256"
_CASES = "escalation_cases"
_CASES_SHA256 = "sha256"
_CHECKS = "candidate_checks"
_OUTCOME = "outcome"


class GateRecordInvalidError(ReleaseCommandError):
    """A record is not one in `supportiq-gate-run/interim-1`."""

    def __init__(self) -> None:
        """Build the error with its fixed message."""
        super().__init__("The gate record is refused: gate_record_invalid.")


@dataclass(frozen=True, slots=True)
class GateRunIdentity:
    """What one gate run was run on.

    Attributes:
        release_id: The ID of the candidate. A release ID gets one gate run, so the run takes
            the same ID.
        manifest_sha256: The SHA-256 of the manifest file of the candidate.
        git_commit: The commit of the repository that the run used.
        case_set: The name of the set of escalation cases.
        cases_sha256: The SHA-256 of the file of the cases.
    """

    release_id: str
    manifest_sha256: str
    git_commit: str
    case_set: str
    cases_sha256: str


@dataclass(frozen=True, slots=True)
class RecordedRun:
    """What publishing reads from the record of a gate run.

    Attributes:
        run_id: The ID of the run.
        release_id: The ID of the candidate that the run ran on.
        manifest_sha256: The SHA-256 of the manifest file of that candidate.
        cases_sha256: The SHA-256 of the file of the cases that the run ran.
        passed: Whether the outcome is `passed`.
        record_sha256: The SHA-256 of the bytes of the record file.
    """

    run_id: str
    release_id: str
    manifest_sha256: str
    cases_sha256: str
    passed: bool
    record_sha256: str


def write_gate_record(records: Path, identity: GateRunIdentity, outcome: GateOutcome) -> Path:
    """Create the folder of records of the release ID, and write the record of the run.

    Args:
        records: The folder of the records of every release, such as `eval/releases/`.
        identity: What the run was run on.
        outcome: Every part of the run.

    Returns:
        The record file.

    Raises:
        ReleaseIdNotFreeError: The folder of records is missing, or a record of the ID exists.
        OSError: The record cannot be written.
    """
    check_release_id_free(records, identity.release_id)
    folder = records / identity.release_id
    try:
        folder.mkdir()
    except FileExistsError as error:
        raise ReleaseIdNotFreeError(ReleaseIdProblem.ALREADY_USED) from error
    record = folder / RECORD_FILE_NAME
    write_json_file(record, gate_record_document(identity, outcome))
    return record


def gate_record_document(identity: GateRunIdentity, outcome: GateOutcome) -> dict[str, object]:
    """Return the JSON document of the record of one run.

    Args:
        identity: What the run was run on.
        outcome: Every part of the run.

    Returns:
        The document, in `supportiq-gate-run/interim-1`.
    """
    return {
        _FORMAT: RECORD_FORMAT,
        _RUN_ID: identity.release_id,
        _RELEASE_ID: identity.release_id,
        _MANIFEST_SHA256: identity.manifest_sha256,
        "git_commit": identity.git_commit,
        _CASES: _cases_part(identity, outcome.cases),
        _CHECKS: [_check_entry(result) for result in outcome.checks],
        "candidate_scope": _scope_part(),
        "guardrails": [_guardrail_entry(result) for result in outcome.guardrails],
        "llm": _llm_part(outcome.llm_calls),
        "test_26": SHARED_SCENARIO_SET_ITEM,
        "known_gaps": list(KNOWN_GAPS),
        _OUTCOME: PASSED if outcome.passed else FAILED,
    }


def read_gate_record(path: Path) -> RecordedRun:
    """Read what publishing needs from the record of a gate run.

    Args:
        path: The record file, `eval/releases/<release_id>/gate-run.json`.

    Returns:
        The IDs, the checksums, and whether the run passed.

    Raises:
        JsonFileInvalidError: The file is missing, a link, unreadable, or not strict JSON.
        GateRecordInvalidError: The record is not in `supportiq-gate-run/interim-1`.
    """
    record = read_json_file(path)
    content = _object(record.content)
    outcome = content.get(_OUTCOME)
    if content.get(_FORMAT) != RECORD_FORMAT or outcome not in {PASSED, FAILED}:
        raise GateRecordInvalidError
    return RecordedRun(
        run_id=_text(content.get(_RUN_ID)),
        release_id=_text(content.get(_RELEASE_ID)),
        manifest_sha256=_text(content.get(_MANIFEST_SHA256)),
        cases_sha256=_text(_object(content.get(_CASES)).get(_CASES_SHA256)),
        passed=outcome == PASSED,
        record_sha256=record.sha256,
    )


def _cases_part(identity: GateRunIdentity, results: tuple[CaseResult, ...]) -> dict[str, object]:
    return {
        "set": identity.case_set,
        _CASES_SHA256: identity.cases_sha256,
        "count": len(results),
        "kinds": dict(sorted(Counter(result.kind.value for result in results).items())),
        "results": [_case_entry(result) for result in results],
    }


def _case_entry(result: CaseResult) -> dict[str, object]:
    failure = (
        {}
        if result.injected_failure is None
        else {"injected_failure": result.injected_failure.value}
    )
    return {
        "case_id": result.case_id,
        "esc_rule": result.esc_rule,
        "kind": result.kind.value,
        **failure,
        "passed": result.passed,
        "mismatches": list(result.mismatches),
    }


def _scope_part() -> dict[str, object]:
    return {
        "on_the_candidate": [_CASES, _CHECKS],
        "not_on_the_candidate": [suite.value for suite in GuardrailSuite],
        "statement": CANDIDATE_SCOPE,
    }


def _llm_part(llm_calls: int) -> dict[str, object]:
    return {"calls": llm_calls, "statement": NO_LLM_CALL if llm_calls == 0 else LLM_CALLED}


def _check_entry(result: CheckResult) -> dict[str, object]:
    return {"check": result.check.value, "passed": result.passed}


def _guardrail_entry(result: GuardrailResult) -> dict[str, object]:
    return {
        "suite": result.suite.value,
        "tests": result.tests,
        "failures": result.failures,
        "errors": result.errors,
        "skipped": result.skipped,
        "test_classnames": list(result.test_classnames),
        "passed": result.passed,
    }


def _object(value: object) -> dict[str, object]:
    # The cast only names the type that `isinstance` found in a JSON value (PY-12).
    if not isinstance(value, dict):
        raise GateRecordInvalidError
    return cast("dict[str, object]", value)


def _text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise GateRecordInvalidError
    return value
