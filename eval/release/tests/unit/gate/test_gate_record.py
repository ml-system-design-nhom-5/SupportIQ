"""The record of a gate run states every part, once per release ID, and no text of a case."""

import hashlib
import json
from pathlib import Path

import pytest

from supportiq_release.candidate.adapters import ReleaseIdNotFreeError, ReleaseIdProblem
from supportiq_release.gate.adapters import (
    RECORD_FILE_NAME,
    GateRecordInvalidError,
    GateRunIdentity,
    RecordedRun,
    gate_record,
    gate_record_document,
    read_gate_record,
    write_gate_record,
)
from supportiq_release.gate.domain import (
    CANDIDATE_SCOPE,
    KNOWN_GAPS,
    KNOWN_GAPS_WITH_KB_DOCUMENTS,
    LLM_CALLS_AS_EXPECTED,
    NO_LLM_CALL,
    SHARED_SCENARIO_SET_ITEM,
    CandidateCheck,
    CaseKind,
    CaseResult,
    CheckResult,
    Failure,
    GateOutcome,
    GuardrailResult,
    GuardrailSuite,
    Mismatch,
)
from tests.unit.gate.fakes import SET_NAME

IDENTITY = GateRunIdentity(
    release_id="fake-release-1",
    manifest_sha256="b" * 64,
    git_commit="c" * 40,
    case_set=SET_NAME,
    cases_sha256="d" * 64,
)
CASES = (
    CaseResult("real", "ESC-04", CaseKind.REAL_MODEL, None, ()),
    CaseResult("injected", "ESC-01", CaseKind.INJECTED_DISTRIBUTION, None, ()),
    CaseResult("failed", "ESC-05", CaseKind.INJECTED_FAILURE, Failure.RETRIEVAL, ()),
    CaseResult("staff", "ESC-01", CaseKind.STAFF_CHOICE, None, ()),
    CaseResult("also-real", "ESC-02", CaseKind.REAL_MODEL, None, ()),
)
CHECKS = tuple(CheckResult(check) for check in CandidateCheck)
AUTHORIZATION_CLASS = "tests.integration.guardrails.test_service_token"
AUDIT_CLASS = "tests.integration.guardrails.test_audit_log"
GUARDRAILS = (
    GuardrailResult(GuardrailSuite.AI_SERVICE, 9, 0, 0, 0, (AUTHORIZATION_CLASS,)),
    GuardrailResult(GuardrailSuite.BACKEND, 21, 0, 0, 0, (AUDIT_CLASS,)),
)
PASSED = GateOutcome(cases=CASES, checks=CHECKS, guardrails=GUARDRAILS, llm_calls=0)
FAILED = GateOutcome(cases=(), checks=CHECKS, guardrails=GUARDRAILS, llm_calls=0)


def test_the_record_identifies_the_candidate_the_commit_and_the_cases() -> None:
    document = gate_record_document(IDENTITY, PASSED)

    assert document["format"] == "supportiq-gate-run/interim-2"
    assert document["run_id"] == document["release_id"] == "fake-release-1"
    assert document["manifest_sha256"] == "b" * 64
    assert document["git_commit"] == "c" * 40
    assert document["escalation_cases"] == {
        "set": SET_NAME,
        "sha256": "d" * 64,
        "count": 5,
        "kinds": {
            "injected_distribution": 1,
            "injected_failure": 1,
            "real_model": 2,
            "staff_choice": 1,
        },
        "results": [
            {
                "case_id": "real",
                "esc_rule": "ESC-04",
                "kind": "real_model",
                "passed": True,
                "mismatches": [],
                "observed": {},
            },
            {
                "case_id": "injected",
                "esc_rule": "ESC-01",
                "kind": "injected_distribution",
                "passed": True,
                "mismatches": [],
                "observed": {},
            },
            {
                "case_id": "failed",
                "esc_rule": "ESC-05",
                "kind": "injected_failure",
                "injected_failure": "retrieval",
                "passed": True,
                "mismatches": [],
                "observed": {},
            },
            {
                "case_id": "staff",
                "esc_rule": "ESC-01",
                "kind": "staff_choice",
                "passed": True,
                "mismatches": [],
                "observed": {},
            },
            {
                "case_id": "also-real",
                "esc_rule": "ESC-02",
                "kind": "real_model",
                "passed": True,
                "mismatches": [],
                "observed": {},
            },
        ],
    }


def test_the_record_states_every_part_the_gaps_and_that_no_llm_call_was_made() -> None:
    document = gate_record_document(IDENTITY, PASSED)

    assert document["candidate_checks"] == [
        {"check": "routes_are_those_of_contract_1_0_0", "passed": True, "observed": []},
        {"check": "no_case_text_in_the_logs", "passed": True, "observed": []},
        {"check": "llm_calls_as_expected", "passed": True, "observed": []},
    ]
    assert document["guardrails"] == [
        {
            "suite": "ai_service_guardrails",
            "tests": 9,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "test_classnames": [AUTHORIZATION_CLASS],
            "passed": True,
        },
        {
            "suite": "backend_guardrails",
            "tests": 21,
            "failures": 0,
            "errors": 0,
            "skipped": 0,
            "test_classnames": [AUDIT_CLASS],
            "passed": True,
        },
    ]
    assert document["llm"] == {"calls": 0, "statement": NO_LLM_CALL}
    assert document["test_26"] == SHARED_SCENARIO_SET_ITEM
    assert document["known_gaps"] == list(KNOWN_GAPS)
    for gap, source in zip(KNOWN_GAPS, ("DATA-23", "CST-02", "ESC-04", "ADR-0025"), strict=True):
        assert source in gap
    assert document["outcome"] == "passed"


def test_a_release_with_kb_documents_records_its_own_gaps() -> None:
    outcome = GateOutcome(
        cases=CASES,
        checks=CHECKS,
        guardrails=GUARDRAILS,
        llm_calls=0,
        known_gaps=KNOWN_GAPS_WITH_KB_DOCUMENTS,
    )

    document = gate_record_document(IDENTITY, outcome)

    assert document["known_gaps"] == list(KNOWN_GAPS_WITH_KB_DOCUMENTS)
    sources = ("DATA-23", "CST-02", "ADR-0025", "ADR-0027", "DATA-48")
    for gap, source in zip(KNOWN_GAPS_WITH_KB_DOCUMENTS, sources, strict=True):
        assert source in gap


def test_the_record_names_the_parts_that_load_the_candidate_and_those_that_do_not() -> None:
    document = gate_record_document(IDENTITY, PASSED)

    assert document["candidate_scope"] == {
        "on_the_candidate": ["escalation_cases", "candidate_checks"],
        "not_on_the_candidate": ["ai_service_guardrails", "backend_guardrails"],
        "statement": CANDIDATE_SCOPE,
    }


def test_a_skipped_guardrail_test_is_recorded_and_fails_the_run() -> None:
    skipped = GuardrailResult(GuardrailSuite.BACKEND, 21, 0, 0, 1, (AUDIT_CLASS,))
    outcome = GateOutcome(
        cases=CASES, checks=CHECKS, guardrails=(GUARDRAILS[0], skipped), llm_calls=0
    )

    document = gate_record_document(IDENTITY, outcome)

    guardrails = document["guardrails"]
    assert isinstance(guardrails, list)
    assert guardrails[1] == {
        "suite": "backend_guardrails",
        "tests": 21,
        "failures": 0,
        "errors": 0,
        "skipped": 1,
        "test_classnames": [AUDIT_CLASS],
        "passed": False,
    }
    assert document["outcome"] == "failed"


def test_an_llm_call_that_no_case_expects_is_recorded_and_fails_the_run() -> None:
    checks = (*CHECKS[:2], CheckResult(CandidateCheck.LLM_CALLS_AS_EXPECTED, ("real", "calls:1")))
    outcome = GateOutcome(cases=CASES, checks=checks, guardrails=GUARDRAILS, llm_calls=1)

    document = gate_record_document(IDENTITY, outcome)

    checks_part = document["candidate_checks"]
    assert isinstance(checks_part, list)
    assert checks_part[2] == {
        "check": "llm_calls_as_expected",
        "passed": False,
        "observed": ["real", "calls:1"],
    }
    assert document["llm"] == {
        "calls": 1,
        "statement": "The LLM step of the gate received a call that the cases do not expect, so"
        " the gate fails (ADR-0021, CI, statement 2).",
    }
    assert document["outcome"] == "failed"


def test_the_calls_that_the_draft_cases_expect_are_recorded_as_such() -> None:
    outcome = GateOutcome(cases=CASES, checks=CHECKS, guardrails=GUARDRAILS, llm_calls=3)

    document = gate_record_document(IDENTITY, outcome)

    assert document["llm"] == {"calls": 3, "statement": LLM_CALLS_AS_EXPECTED}
    assert document["outcome"] == "passed"


def test_a_failed_case_is_recorded_with_its_mismatches() -> None:
    failed = CaseResult(
        "real", "ESC-04", CaseKind.REAL_MODEL, None, (Mismatch("createDraft.llm_called", "true"),)
    )
    outcome = GateOutcome(cases=(failed,), checks=CHECKS, guardrails=GUARDRAILS, llm_calls=0)

    document = gate_record_document(IDENTITY, outcome)

    cases = document["escalation_cases"]
    assert isinstance(cases, dict)
    assert cases["results"] == [
        {
            "case_id": "real",
            "esc_rule": "ESC-04",
            "kind": "real_model",
            "passed": False,
            "mismatches": ["createDraft.llm_called"],
            "observed": {"createDraft.llm_called": "true"},
        }
    ]
    assert document["outcome"] == "failed"


def test_the_record_is_written_once_into_a_new_folder_of_its_release_id(tmp_path: Path) -> None:
    record = write_gate_record(tmp_path, IDENTITY, PASSED)

    assert record == tmp_path / "fake-release-1" / RECORD_FILE_NAME
    assert json.loads(record.read_text()) == gate_record_document(IDENTITY, PASSED)
    with pytest.raises(ReleaseIdNotFreeError) as refused:
        write_gate_record(tmp_path, IDENTITY, PASSED)
    assert refused.value.problem is ReleaseIdProblem.ALREADY_USED
    assert [path.name for path in record.parent.iterdir()] == [RECORD_FILE_NAME]


def test_a_folder_made_between_the_check_and_the_write_is_never_written_into(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Another run takes the release ID after the check: the exclusive folder still refuses it.
    def taken_after_the_check(records: Path, release_id: str) -> None:
        (records / release_id).mkdir()

    monkeypatch.setattr(gate_record, "check_release_id_free", taken_after_the_check)

    with pytest.raises(ReleaseIdNotFreeError) as refused:
        write_gate_record(tmp_path, IDENTITY, PASSED)

    assert refused.value.problem is ReleaseIdProblem.ALREADY_USED
    assert not any((tmp_path / "fake-release-1").iterdir())


def test_no_record_is_written_without_the_folder_of_records(tmp_path: Path) -> None:
    with pytest.raises(ReleaseIdNotFreeError):
        write_gate_record(tmp_path / "absent", IDENTITY, PASSED)

    assert not (tmp_path / "absent").exists()


@pytest.mark.parametrize(("outcome", "passed"), [(PASSED, True), (FAILED, False)])
def test_a_written_record_reads_back_with_its_ids_checksums_and_outcome(
    tmp_path: Path, outcome: GateOutcome, passed: bool
) -> None:
    record = write_gate_record(tmp_path, IDENTITY, outcome)

    run = read_gate_record(record)

    assert run == RecordedRun(
        run_id="fake-release-1",
        release_id="fake-release-1",
        manifest_sha256="b" * 64,
        cases_sha256="d" * 64,
        passed=passed,
        record_sha256=hashlib.sha256(record.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"format": "supportiq-gate-run/interim-1"},
        {"outcome": "skipped"},
        {"run_id": ""},
        {"release_id": 1},
        {"manifest_sha256": None},
        {"escalation_cases": []},
        {"escalation_cases": {"set": SET_NAME}},
    ],
    ids=[
        "the format before the draft path",
        "another outcome",
        "an empty run ID",
        "a release ID not a text",
        "no manifest checksum",
        "cases not an object",
        "no cases checksum",
    ],
)
def test_a_record_of_another_shape_is_refused(tmp_path: Path, change: dict[str, object]) -> None:
    path = tmp_path / "gate-run.json"
    path.write_text(json.dumps({**gate_record_document(IDENTITY, PASSED), **change}))

    with pytest.raises(GateRecordInvalidError) as refused:
        read_gate_record(path)

    assert str(refused.value) == "The gate record is refused: gate_record_invalid."


def test_a_record_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "gate-run.json"
    path.write_text("[]")

    with pytest.raises(GateRecordInvalidError):
        read_gate_record(path)
