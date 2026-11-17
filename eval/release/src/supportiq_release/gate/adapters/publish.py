"""Publish a candidate that passed the gate: copy it, and link its gate run in its manifest.

A candidate is published only when the record of its gate run passed, names the same release
ID and the same manifest bytes, and ran the escalation cases with the SHA-256 of the set as it
is, which the caller has checked against the approval of the set (DATA-57; ADR-0021, Exception
to TEST-26). The published manifest is the candidate manifest with `gate_run`, which
`verify_release` of `ai-service` then accepts.

Publishing has two steps, so that a release is linked only once it exists:

1. `prepare_release` checks the record and writes the release into a folder, the staging
   folder of the command, which the command then moves to the output.
2. `link_release` writes the same manifest next to the record, once the release folder is in
   place, where a CI check of ADR-0021 (Release and the offline evaluation gate, statement 2)
   is to read it. That manifest is never replaced, so a release ID is published once, and a
   move that fails leaves no link, so the command can run again (ERR-04).
"""

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import cast

from supportiq_ai_service.release.manifest import verify_candidate, verify_release

from supportiq_release.candidate.adapters import PlannedCopy, copy_files
from supportiq_release.candidate.domain import MANIFEST_FILE_NAME, AssetName, is_release_path
from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import JsonFile, read_json_file, write_json_file
from supportiq_release.gate.adapters.gate_record import (
    PASSED,
    RECORD_FILE_NAME,
    RecordedRun,
    read_gate_record,
)


class PublishProblem(StrEnum):
    """Why a candidate is not published."""

    NOT_PASSED = "gate_run_not_passed"
    OTHER_CANDIDATE = "gate_run_of_another_candidate"
    OTHER_CASES = "gate_run_of_other_cases"
    RECORDS_PATH_INVALID = "release_records_not_a_relative_path"
    ALREADY_PUBLISHED = "release_already_published"


class PublishRefusedError(ReleaseCommandError):
    """A candidate is not published. The message names the problem only."""

    def __init__(self, problem: PublishProblem) -> None:
        """Build the error with a message that names the problem.

        Args:
            problem: Why the candidate is not published.
        """
        super().__init__(f"The candidate is not published: {problem}.")
        self.problem = problem


@dataclass(frozen=True, slots=True)
class PreparedRelease:
    """A release written into its folder, waiting to be linked next to its record.

    Attributes:
        release_id: The release ID.
        manifest: The published manifest, with `gate_run`.
    """

    release_id: str
    manifest: dict[str, object]


def prepare_release(
    candidate: Path, records: Path, cases_sha256: str, output: Path
) -> PreparedRelease:
    """Check the record of a candidate, and write the release into a new, empty folder.

    Args:
        candidate: The folder of the candidate.
        records: The folder of the records of every release, relative to the repository root.
        cases_sha256: The SHA-256 of the file of the approved cases as it is now.
        output: The new, empty folder of the release.

    Returns:
        The release, for `link_release` once the folder is in place.

    Raises:
        PublishRefusedError: The records are not a relative path, the record did not pass, is
            of another candidate, or ran other cases, or the release ID is already published.
        GateRecordInvalidError: The record is not in `supportiq-gate-run/interim-1`.
        ReleaseInvalidError: `ai-service` refuses the candidate or the published release.
        JsonFileInvalidError: The manifest or the record is missing or not strict JSON.
    """
    if records.is_absolute() or not is_release_path(records.as_posix()):
        raise PublishRefusedError(PublishProblem.RECORDS_PATH_INVALID)
    manifest_file = read_json_file(candidate / MANIFEST_FILE_NAME)
    release_id = verify_candidate(candidate / MANIFEST_FILE_NAME).manifest.release_id
    run = read_gate_record(records / release_id / RECORD_FILE_NAME)
    _check_run(run, release_id, manifest_file.sha256, cases_sha256)
    beside_the_record = records / release_id / MANIFEST_FILE_NAME
    if beside_the_record.exists() or beside_the_record.is_symlink():
        raise PublishRefusedError(PublishProblem.ALREADY_PUBLISHED)
    copy_files(_copies(candidate, manifest_file), output)
    published = {**_manifest(manifest_file), "gate_run": _gate_run(records, run, release_id)}
    manifest = output / MANIFEST_FILE_NAME
    write_json_file(manifest, published)
    verify_release(manifest)
    return PreparedRelease(release_id=release_id, manifest=published)


def link_release(records: Path, release: PreparedRelease) -> Path:
    """Write the published manifest next to the record, once the release folder is in place.

    Args:
        records: The folder of the records of every release.
        release: The release that `prepare_release` wrote.

    Returns:
        The manifest next to the record.

    Raises:
        PublishRefusedError: The release ID was published in the meantime.
        OSError: The manifest cannot be written.
    """
    beside_the_record = records / release.release_id / MANIFEST_FILE_NAME
    try:
        write_json_file(beside_the_record, release.manifest)
    except FileExistsError as error:
        raise PublishRefusedError(PublishProblem.ALREADY_PUBLISHED) from error
    return beside_the_record


def _check_run(run: RecordedRun, release_id: str, manifest_sha256: str, cases_sha256: str) -> None:
    if not run.passed:
        raise PublishRefusedError(PublishProblem.NOT_PASSED)
    if (run.release_id, run.manifest_sha256) != (release_id, manifest_sha256):
        raise PublishRefusedError(PublishProblem.OTHER_CANDIDATE)
    if run.cases_sha256 != cases_sha256:
        raise PublishRefusedError(PublishProblem.OTHER_CASES)


def _gate_run(records: Path, run: RecordedRun, release_id: str) -> dict[str, object]:
    record = PurePosixPath(records.as_posix(), release_id, RECORD_FILE_NAME)
    return {
        "run_id": run.run_id,
        "outcome": PASSED,
        "record": record.as_posix(),
        "record_sha256": run.record_sha256,
    }


# `verify_candidate` checked the manifest, so each value has the shape that the casts name (PY-12).
def _manifest(manifest_file: JsonFile) -> dict[str, object]:
    return cast("dict[str, object]", manifest_file.content)


def _copies(candidate: Path, manifest_file: JsonFile) -> tuple[PlannedCopy, ...]:
    assets = cast("dict[str, dict[str, object]]", _manifest(manifest_file)["assets"])
    return tuple(
        PlannedCopy(asset=AssetName(name), source=candidate / path, path=path)
        for name, asset in assets.items()
        for path in _paths(asset)
    )


def _paths(asset: dict[str, object]) -> list[str]:
    entries = cast("list[dict[str, object]]", asset["files"])
    return [cast("str", entry["path"]) for entry in entries]
