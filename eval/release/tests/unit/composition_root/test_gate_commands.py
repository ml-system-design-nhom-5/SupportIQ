"""`run-gate` and `publish-candidate`: exit statuses, the record, and the approval of the cases.

The application of the candidate is the fake of `tests/unit/gate/fakes.py`, because the real
models need torch. It reads its service token from the environment when it is built, as
`ai-service` does, so these tests also show that the command sets the settings of the run. The
rest of each command runs as it is.
"""

import json
import os
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from supportiq_release.composition_root import cli, gate_commands
from supportiq_release.gate.adapters import (
    CandidateRun,
    GatePorts,
    candidate_settings,
    run_cases,
)
from supportiq_release.gate.domain import Case
from tests.unit.candidate.fakes import RELEASE_ID
from tests.unit.gate.fakes import (
    GUARDRAIL_CLASSNAME,
    LLM_MESSAGE,
    MESSAGE,
    WRITTEN_FOR,
    build_fake_candidate,
    case_document,
    expected_document,
    fake_application_factory,
    junit_xml,
    set_document,
    write_set,
)

GIT_COMMIT = "c" * 40
# The exit statuses that the README documents, as numbers, so a changed constant fails.
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_INPUT_INVALID = 2
# The value of each setting of the gate before a run, which the run must replace.
BEFORE_THE_RUN = "set-before-the-run"


@dataclass
class FakeCandidate:
    """How the fake application of the candidate behaves in one test."""

    leak_message: bool = False
    extra_route: str | None = None
    failure: Exception | None = None
    built: dict[str, object] = field(default_factory=dict[str, object])


@pytest.fixture(autouse=True)
def settings_of_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each setting that the run sets is set here first, so the test restores the environment.
    for name in candidate_settings(BEFORE_THE_RUN):
        monkeypatch.setenv(name, BEFORE_THE_RUN)


@pytest.fixture(autouse=True)
def fake_candidate(monkeypatch: pytest.MonkeyPatch) -> FakeCandidate:
    fake = FakeCandidate()

    def run(
        manifest_path: Path, cases: Sequence[Case], ports: GatePorts, service_token: str
    ) -> CandidateRun:
        if fake.failure is not None:
            raise fake.failure
        build = fake_application_factory(
            leak_message=fake.leak_message, extra_route=fake.extra_route, built=fake.built
        )
        return run_cases(manifest_path, cases, ports, service_token, build=build)

    monkeypatch.setattr(gate_commands, "run_cases", run)
    return fake


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # The records are named relative to the repository root, here the folder of the test.
    monkeypatch.chdir(tmp_path)
    build_fake_candidate(tmp_path)
    write_set(tmp_path / "set")
    _write_junit(tmp_path)
    return tmp_path


def _write_junit(base: Path, backend: bytes | None = None) -> None:
    (base / "ai-service.xml").write_bytes(junit_xml(tests=9, name="ai_service_guardrails"))
    (base / "backend.xml").write_bytes(junit_xml(tests=21) if backend is None else backend)


def _run_gate(git_commit: str = GIT_COMMIT) -> int:
    return cli.main(
        [
            "run-gate",
            "--candidate",
            "candidate",
            "--cases",
            "set/cases.json",
            "--ai-service-guardrails",
            "ai-service.xml",
            "--backend-guardrails",
            "backend.xml",
            "--git-commit",
            git_commit,
            "--release-records",
            "releases",
        ]
    )


def _publish(output: str = "release") -> int:
    return cli.main(
        [
            "publish-candidate",
            "--candidate",
            "candidate",
            "--cases",
            "set/cases.json",
            "--release-records",
            "releases",
            "--output",
            output,
        ]
    )


def _record_path(workspace: Path) -> Path:
    return workspace / "releases" / RELEASE_ID / "gate-run.json"


def _record(workspace: Path) -> dict[str, object]:
    return json.loads(_record_path(workspace).read_text())


# The casts below only name the shapes that `gate_record.py` writes (PY-12).
def _object(value: object) -> dict[str, object]:
    return cast("dict[str, object]", value)


def _entries(value: object) -> list[dict[str, object]]:
    return cast("list[dict[str, object]]", value)


def _checks(workspace: Path) -> dict[object, object]:
    entries = _entries(_record(workspace)["candidate_checks"])
    return {entry["check"]: entry["passed"] for entry in entries}


def test_a_gate_run_that_passes_exits_0_and_records_the_run(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status = _run_gate()

    record = _record(workspace)
    assert status == EXIT_PASSED
    assert capsys.readouterr().out == (
        f"release_id={RELEASE_ID} cases=1 failed_cases=0 outcome=passed"
        f" record=releases/{RELEASE_ID}/gate-run.json\n"
    )
    assert record["outcome"] == "passed"
    assert record["git_commit"] == GIT_COMMIT
    cases = record["escalation_cases"]
    assert isinstance(cases, dict)
    assert cases["sha256"] == gate_commands.read_cases_file(Path("set/cases.json")).sha256


def test_the_run_sets_a_new_service_token_and_unused_llm_settings_before_the_candidate_is_built(
    workspace: Path, fake_candidate: FakeCandidate
) -> None:
    assert _run_gate() == EXIT_PASSED

    token = os.environ["SERVICE_TOKEN"]
    assert token != BEFORE_THE_RUN
    assert fake_candidate.built["service_token"] == token
    assert dict(os.environ) | candidate_settings(token) == dict(os.environ)
    assert _record(workspace)["outcome"] == "passed"


def test_a_case_that_fails_fails_the_gate_with_status_1_and_still_records_the_run(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    case = case_document(expected=expected_document(recommendation="escalate"))
    write_set(workspace / "set", set_document(case))

    status = _run_gate()

    assert status == EXIT_FAILED
    assert "failed_cases=1 outcome=failed" in capsys.readouterr().out
    assert _record(workspace)["outcome"] == "failed"


def test_a_log_that_holds_the_message_fails_the_gate(
    workspace: Path, fake_candidate: FakeCandidate
) -> None:
    fake_candidate.leak_message = True

    assert _run_gate() == EXIT_FAILED
    assert _checks(workspace) == {
        "routes_are_those_of_contract_1_0_0": True,
        "no_case_text_in_the_logs": False,
        "no_llm_call": True,
    }


def test_a_route_outside_the_contract_fails_the_gate(
    workspace: Path, fake_candidate: FakeCandidate
) -> None:
    fake_candidate.extra_route = "/v1/refunds"

    assert _run_gate() == EXIT_FAILED
    assert _checks(workspace) == {
        "routes_are_those_of_contract_1_0_0": False,
        "no_case_text_in_the_logs": True,
        "no_llm_call": True,
    }


def test_a_call_of_the_llm_step_fails_the_gate_even_when_the_case_expects_it(
    workspace: Path,
) -> None:
    case = case_document(
        request={"message": LLM_MESSAGE, "as_of": "2026-11-17T09:00:00Z"},
        expected=expected_document(no_other_reason_codes=False, llm_called=True),
    )
    write_set(workspace / "set", set_document(case))

    status = _run_gate()

    record = _record(workspace)
    assert status == EXIT_FAILED
    assert _entries(_object(record["escalation_cases"])["results"])[0]["passed"] is True
    assert _checks(workspace)["no_llm_call"] is False
    assert record["llm"] == {
        "calls": 1,
        "statement": "The LLM step of the gate received a call, so the gate fails"
        " (ADR-0021, CI, statement 2).",
    }


def test_the_record_holds_no_text_of_a_case(workspace: Path) -> None:
    failing = case_document(expected=expected_document(recommendation="escalate"))
    write_set(workspace / "set", set_document(failing))

    assert _run_gate() == EXIT_FAILED

    text = _record_path(workspace).read_text()
    assert MESSAGE not in text
    assert "[ORDER_ID_1]" not in text
    assert "Where is" not in text


def test_a_skipped_guardrail_test_fails_the_gate_and_is_recorded(workspace: Path) -> None:
    _write_junit(workspace, backend=junit_xml(tests=21, skipped=1))

    status = _run_gate()

    record = _record(workspace)
    assert status == EXIT_FAILED
    assert record["outcome"] == "failed"
    guardrails = record["guardrails"]
    assert isinstance(guardrails, list)
    assert guardrails[1] == {
        "suite": "backend_guardrails",
        "tests": 21,
        "failures": 0,
        "errors": 0,
        "skipped": 1,
        "test_classnames": [GUARDRAIL_CLASSNAME],
        "passed": False,
    }


def test_a_report_of_the_other_folder_stops_the_gate_without_a_record(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (workspace / "backend.xml").write_bytes(junit_xml(tests=9, name="ai_service_guardrails"))

    assert _run_gate() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == (
        "The result of backend_guardrails is refused: report_of_another_suite.\n"
    )
    assert not any((workspace / "releases").iterdir())


def test_a_release_id_is_run_once(workspace: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _run_gate() == EXIT_PASSED
    capsys.readouterr()

    assert _run_gate() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err.startswith("The ")
    assert _record(workspace)["outcome"] == "passed"


@pytest.mark.parametrize(
    "approval",
    [
        {"status": "draft", "approved_by": None, "approved_on": None},
        {"cases_sha256": "a" * 64},
        {"approved_on": None},
    ],
    ids=["draft", "other bytes", "no date"],
)
def test_cases_that_are_not_approved_as_they_are_stop_the_gate_without_a_record(
    workspace: Path, capsys: pytest.CaptureFixture[str], approval: dict[str, object]
) -> None:
    write_set(workspace / "set", approval=approval)

    status = _run_gate()

    assert status == EXIT_INPUT_INVALID
    assert capsys.readouterr().err.startswith("The escalation cases are not approved: ")
    assert not any((workspace / "releases").iterdir())


def test_cases_changed_after_their_approval_stop_the_gate(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = workspace / "set" / "cases.json"
    cases.write_bytes(cases.read_bytes() + b"\n")

    assert _run_gate() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == (
        "The escalation cases are not approved: cases_not_those_of_the_approval.\n"
    )


def test_cases_written_for_another_release_stop_the_gate_and_name_the_fields(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    written_for = {**WRITTEN_FOR, "model_version": "fake-model-2", "kb_document_count": 3}
    write_set(workspace / "set", set_document(written_for=written_for))

    status = _run_gate()

    assert status == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == (
        "The escalation cases are not written for this candidate:"
        " model_version, kb_document_count.\n"
    )
    assert not any((workspace / "releases").iterdir())


def test_a_guardrail_result_that_cannot_be_read_stops_the_gate(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (workspace / "backend.xml").unlink()

    assert _run_gate() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == (
        "The result of backend_guardrails is refused: missing_or_not_a_regular_file.\n"
    )


@pytest.mark.parametrize("git_commit", ["c" * 39, "C" * 40, "HEAD"])
def test_the_commit_must_be_its_40_hexadecimal_characters(workspace: Path, git_commit: str) -> None:
    with pytest.raises(SystemExit) as stopped:
        _run_gate(git_commit)

    assert stopped.value.code == EXIT_INPUT_INVALID
    assert not any((workspace / "releases").iterdir())


def test_a_record_that_cannot_be_written_exits_2_and_names_only_the_type(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_space(*arguments: object) -> Path:
        del arguments
        message = f"no space left for {workspace}"
        raise OSError(message)

    monkeypatch.setattr(gate_commands, "write_gate_record", no_space)

    assert _run_gate() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The command stopped on an unexpected OSError.\n"


def test_an_unexpected_error_of_the_candidate_exits_2_and_names_only_the_type(
    workspace: Path, capsys: pytest.CaptureFixture[str], fake_candidate: FakeCandidate
) -> None:
    fake_candidate.failure = RuntimeError(f"a confidential {MESSAGE}")

    assert _run_gate() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The command stopped on an unexpected RuntimeError.\n"
    assert not any((workspace / "releases").iterdir())


def test_a_candidate_that_passed_is_published(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_gate() == EXIT_PASSED
    capsys.readouterr()

    status = _publish()

    manifest = json.loads((workspace / "release" / "release-manifest.json").read_text())
    beside_the_record = workspace / "releases" / RELEASE_ID / "release-manifest.json"
    assert status == EXIT_PASSED
    assert capsys.readouterr().out == "published=release\n"
    assert manifest["gate_run"]["record"] == f"releases/{RELEASE_ID}/gate-run.json"
    assert json.loads(beside_the_record.read_text()) == manifest


def test_a_move_that_fails_leaves_no_link_so_publishing_can_run_again(
    workspace: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run_gate() == EXIT_PASSED
    beside_the_record = workspace / "releases" / RELEASE_ID / "release-manifest.json"
    replace = Path.replace

    def failing_move(self: Path, target: str | Path) -> Path:
        if Path(target).name == "release":
            message = "the move failed"
            raise OSError(message)
        return replace(self, target)

    capsys.readouterr()
    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", failing_move)
        failed = _publish()
    failed_err = capsys.readouterr().err

    assert failed == EXIT_INPUT_INVALID
    assert failed_err == "The output folder is refused: not_writable.\n"
    assert not (workspace / "release").exists()
    assert not beside_the_record.exists()
    assert _publish() == EXIT_PASSED
    assert beside_the_record.exists()


def test_a_release_is_published_once_and_never_into_a_used_folder(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_gate() == EXIT_PASSED
    used = workspace / "used"
    used.mkdir()
    (used / "kept").write_text("kept")
    capsys.readouterr()

    into_a_used_folder = _publish("used")
    first = _publish()
    capsys.readouterr()
    again = _publish("again")

    assert into_a_used_folder == EXIT_INPUT_INVALID
    assert [path.name for path in used.iterdir()] == ["kept"]
    assert first == EXIT_PASSED
    assert again == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == (
        "The candidate is not published: release_already_published.\n"
    )
    assert not (workspace / "again").exists()


def test_a_candidate_whose_run_failed_is_not_published(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_junit(workspace, backend=junit_xml(tests=21, failures=1))
    assert _run_gate() == EXIT_FAILED
    capsys.readouterr()

    assert _publish() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The candidate is not published: gate_run_not_passed.\n"
    assert not (workspace / "release").exists()


def test_cases_whose_approval_was_withdrawn_are_not_published(
    workspace: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert _run_gate() == EXIT_PASSED
    write_set(
        workspace / "set", approval={"status": "draft", "approved_by": None, "approved_on": None}
    )
    capsys.readouterr()

    assert _publish() == EXIT_INPUT_INVALID
    assert capsys.readouterr().err == "The escalation cases are not approved: cases_not_frozen.\n"
    assert not (workspace / "release").exists()
