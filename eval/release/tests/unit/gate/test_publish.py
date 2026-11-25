"""A candidate is published only with a passing record of itself and of the cases as they are."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import pytest
from app.release.manifest import verify_release

from supportiq_release.files import JsonFileInvalidError
from supportiq_release.gate.adapters import (
    GateRecordInvalidError,
    GateRunIdentity,
    PublishProblem,
    PublishRefusedError,
    link_release,
    prepare_release,
    write_gate_record,
)
from supportiq_release.gate.domain import (
    CandidateCheck,
    CaseKind,
    CaseResult,
    CheckResult,
    GateOutcome,
    GuardrailResult,
    GuardrailSuite,
    Mismatch,
)
from tests.unit.candidate.fakes import RELEASE_FILES, RELEASE_ID
from tests.unit.gate.fakes import SET_NAME, build_fake_candidate

RECORDS = Path("releases")
CASES_SHA256 = "d" * 64
PASSED = GateOutcome(
    cases=(CaseResult("real", "ESC-04", CaseKind.REAL_MODEL, None, ()),),
    checks=tuple(CheckResult(check) for check in CandidateCheck),
    guardrails=tuple(GuardrailResult(suite, 3, 0, 0, 0) for suite in GuardrailSuite),
    llm_calls=0,
)
BESIDE_THE_RECORD = RECORDS / RELEASE_ID / "release-manifest.json"


@pytest.fixture
def candidate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # The records are named relative to the repository root, here the folder of the test.
    monkeypatch.chdir(tmp_path)
    return build_fake_candidate(tmp_path)


@pytest.fixture
def output(tmp_path: Path) -> Path:
    folder = tmp_path / "release"
    folder.mkdir()
    return folder


def _record(candidate: Path, outcome: GateOutcome = PASSED) -> Path:
    manifest = candidate / "release-manifest.json"
    identity = GateRunIdentity(
        release_id=RELEASE_ID,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        git_commit="c" * 40,
        case_set=SET_NAME,
        cases_sha256=CASES_SHA256,
    )
    return write_gate_record(RECORDS, identity, outcome)


def _change(record: Path, **fields: object) -> None:
    record.write_text(json.dumps({**json.loads(record.read_text()), **fields}))


def test_a_candidate_that_passed_is_written_and_then_linked_next_to_its_record(
    candidate: Path, output: Path
) -> None:
    record = _record(candidate)

    release = prepare_release(candidate, RECORDS, CASES_SHA256, output)

    manifest = output / "release-manifest.json"
    published = json.loads(manifest.read_text())
    assert release.release_id == RELEASE_ID
    assert release.manifest == published
    assert published["gate_run"] == {
        "run_id": RELEASE_ID,
        "outcome": "passed",
        "record": f"releases/{RELEASE_ID}/gate-run.json",
        "record_sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
    }
    candidate_manifest = json.loads((candidate / "release-manifest.json").read_text())
    assert candidate_manifest["gate_run"] is None
    assert published == {**candidate_manifest, "gate_run": published["gate_run"]}
    assert verify_release(manifest).current().versions.release_id == RELEASE_ID
    for path in RELEASE_FILES.values():
        assert (output / path).read_bytes() == (candidate / path).read_bytes()
    # Nothing is linked until the release folder is in place.
    assert not BESIDE_THE_RECORD.exists()

    assert link_release(RECORDS, release) == BESIDE_THE_RECORD
    assert json.loads(BESIDE_THE_RECORD.read_text()) == published


def test_the_run_id_comes_from_the_record(candidate: Path, output: Path) -> None:
    _change(_record(candidate), run_id="fake-run-7")

    release = prepare_release(candidate, RECORDS, CASES_SHA256, output)

    gate_run = release.manifest["gate_run"]
    assert isinstance(gate_run, dict)
    assert gate_run["run_id"] == "fake-run-7"


def _failed(candidate: Path) -> None:
    failed_case = CaseResult(
        "real", "ESC-04", CaseKind.REAL_MODEL, None, (Mismatch("createDraft.x", "y"),)
    )
    _record(candidate, GateOutcome((failed_case,), PASSED.checks, PASSED.guardrails, 0))


def _of_another_manifest(candidate: Path) -> None:
    _change(_record(candidate), manifest_sha256="e" * 64)


def _of_another_release_id(candidate: Path) -> None:
    # A record copied from the folder of another release ID into the folder of this one.
    _change(_record(candidate), release_id="fake-release-2")


def _of_other_cases(candidate: Path) -> None:
    record = _record(candidate)
    cases = {**json.loads(record.read_text())["escalation_cases"], "sha256": "f" * 64}
    _change(record, escalation_cases=cases)


@pytest.mark.parametrize(
    ("change", "problem"),
    [
        (_failed, PublishProblem.NOT_PASSED),
        (_of_another_manifest, PublishProblem.OTHER_CANDIDATE),
        (_of_another_release_id, PublishProblem.OTHER_CANDIDATE),
        (_of_other_cases, PublishProblem.OTHER_CASES),
    ],
)
def test_a_record_that_does_not_cover_the_candidate_and_the_cases_is_refused(
    candidate: Path, output: Path, change: Callable[[Path], None], problem: PublishProblem
) -> None:
    change(candidate)

    with pytest.raises(PublishRefusedError) as refused:
        prepare_release(candidate, RECORDS, CASES_SHA256, output)

    assert refused.value.problem is problem
    assert not any(output.iterdir())


def test_a_record_of_another_format_is_refused(candidate: Path, output: Path) -> None:
    # `interim-1` is the format of the record of the first release, before the draft path.
    _change(_record(candidate), format="supportiq-gate-run/interim-1")

    with pytest.raises(GateRecordInvalidError):
        prepare_release(candidate, RECORDS, CASES_SHA256, output)

    assert not any(output.iterdir())


def test_a_release_id_is_published_once(candidate: Path, output: Path, tmp_path: Path) -> None:
    _record(candidate)
    link_release(RECORDS, prepare_release(candidate, RECORDS, CASES_SHA256, output))
    published = BESIDE_THE_RECORD.read_bytes()
    second = tmp_path / "second"
    second.mkdir()

    with pytest.raises(PublishRefusedError) as refused:
        prepare_release(candidate, RECORDS, CASES_SHA256, second)

    assert refused.value.problem is PublishProblem.ALREADY_PUBLISHED
    assert not any(second.iterdir())
    assert BESIDE_THE_RECORD.read_bytes() == published


def test_a_release_linked_meanwhile_is_never_replaced(candidate: Path, output: Path) -> None:
    _record(candidate)
    release = prepare_release(candidate, RECORDS, CASES_SHA256, output)
    BESIDE_THE_RECORD.write_text("{}")

    with pytest.raises(PublishRefusedError) as refused:
        link_release(RECORDS, release)

    assert refused.value.problem is PublishProblem.ALREADY_PUBLISHED
    assert BESIDE_THE_RECORD.read_text() == "{}"


def test_a_candidate_without_a_record_is_refused(candidate: Path, output: Path) -> None:
    with pytest.raises(JsonFileInvalidError):
        prepare_release(candidate, RECORDS, CASES_SHA256, output)


@pytest.mark.parametrize("records", ["absolute", "../releases"])
def test_records_that_are_not_a_path_in_the_repository_are_refused(
    candidate: Path, output: Path, tmp_path: Path, records: str
) -> None:
    _record(candidate)
    path = tmp_path / RECORDS if records == "absolute" else Path(records)

    with pytest.raises(PublishRefusedError) as refused:
        prepare_release(candidate, path, CASES_SHA256, output)

    assert refused.value.problem is PublishProblem.RECORDS_PATH_INVALID
