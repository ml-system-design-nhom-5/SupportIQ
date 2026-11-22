"""The command line of the release command: `supportiq-release <command>` (ARCH-21).

- `ingest-kb` reads a raw KB folder and writes the KB, the document-to-intent mapping, and the
  report of the ingestion (ADR-0021, KB ingestion). A run that quarantines a record, or finds
  a released version missing from the KB file, fails until an issue accepts it (DATA-13): it
  still writes its files, and it exits with status 3 unless `--accepted-quarantine` names
  that issue.
- `build-candidate` copies the six assets that a spec names into a new folder, writes the
  manifest of a candidate, and checks it as `ai-service` checks a release (ADR-0021, Release
  and the offline evaluation gate). The candidate has no gate run, so no replica serves it.
- `run-gate` and `publish-candidate` run the offline evaluation gate on a candidate and
  publish a candidate that passed it (`gate_commands.py`).
- `pack-release`, `download-release`, and `check-pinned-release` write, download, and check
  the archive of a published release (`distribution_commands.py`, ADR-0030).

Every expected failure is an error of the root `ReleaseCommandError` or a `ReleaseInvalidError`
of `ai-service`: the command prints its message and exits with status 2, and the output folder
is left as it was. Three roots of the release download have their own status: a declined
download 4, a failed request 5, and a failed check of a release 6. Any other failure, such as a
file that cannot be written, prints only the name of its type and exits with status 2 too, so
status 1 always means a gate run that failed. Nothing that the command prints holds text of the
KB or a secret.
"""

import argparse
import re
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from app.release.manifest import ReleaseInvalidError

from supportiq_release.candidate.adapters import (
    check_kb_versions,
    check_release_id_free,
    copy_files,
    plan_copies,
    read_release_spec,
    write_candidate_manifest,
)
from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.composition_root.distribution_commands import (
    add_distribution_commands,
    check_pinned_release,
    download_release,
    pack_release,
)
from supportiq_release.composition_root.exit_statuses import (
    EXIT_CHECK_FAILED,
    EXIT_DECLINED,
    EXIT_INPUT_INVALID,
    EXIT_NETWORK_FAILED,
    EXIT_QUARANTINE_NOT_ACCEPTED,
    EXIT_SUCCESS,
)
from supportiq_release.composition_root.gate_commands import add_gate_commands, publish, run_gate
from supportiq_release.errors import (
    DownloadDeclinedError,
    NetworkFailedError,
    ReleaseCheckFailedError,
    ReleaseCommandError,
)
from supportiq_release.files import describe_release_refusal, new_output_folder
from supportiq_release.kb_ingestion.adapters import (
    content_sha256,
    read_intent_labels,
    read_raw_kb_folder,
    write_ingestion,
)
from supportiq_release.kb_ingestion.domain import admit

_ISSUE_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*")
# The roots of the release download that have a status of their own; every other is 2.
_STATUS_BY_ROOT_ERROR: tuple[tuple[type[ReleaseCommandError], int], ...] = (
    (DownloadDeclinedError, EXIT_DECLINED),
    (NetworkFailedError, EXIT_NETWORK_FAILED),
    (ReleaseCheckFailedError, EXIT_CHECK_FAILED),
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command of the release command.

    Args:
        argv: The arguments after the program name; the process arguments when None.

    Returns:
        The exit status: 0 when the command succeeded, 1 when a gate run failed, 2 for an
        input that cannot be used or a candidate that `ai-service` refuses, 3 when
        quarantined records wait for an issue that accepts them, and for the release download
        4 when it is declined, 5 when a request to GitHub fails, and 6 when a check fails.
    """
    arguments = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    commands: dict[str, Callable[[argparse.Namespace], int]] = {
        "ingest-kb": _ingest_kb,
        "build-candidate": _build,
        "run-gate": run_gate,
        "publish-candidate": publish,
        "pack-release": pack_release,
        "download-release": download_release,
        "check-pinned-release": check_pinned_release,
    }
    try:
        return commands[arguments.command](arguments)
    except ReleaseCommandError as error:
        sys.stderr.write(f"{error}\n")
        return _status_of(error)
    except ReleaseInvalidError as error:
        # The reason, the asset, and the path inside the release, never the content of a file.
        sys.stderr.write(f"{describe_release_refusal(error)}\n")
    except Exception as error:  # the top of the process (PY-21): status 2, never 1
        # Only the type: the message of an unexpected error could hold any text.
        sys.stderr.write(f"The command stopped on an unexpected {type(error).__name__}.\n")
    return EXIT_INPUT_INVALID


def _ingest_kb(arguments: argparse.Namespace) -> int:
    kb_folder, intent_labels = Path(arguments.kb_folder), Path(arguments.intent_labels)
    folder = read_raw_kb_folder(kb_folder)
    result = admit(folder.kb, read_intent_labels(intent_labels), content_sha256)
    accepted_in: str | None = arguments.accepted_quarantine
    with new_output_folder(Path(arguments.output), (kb_folder, intent_labels)) as staging:
        write_ingestion(staging, folder, result, accepted_in)
    accepted = accepted_in is not None or not result.needs_accepted_quarantine
    sys.stdout.write(
        f"kb_version={result.kb_version} admitted={len(result.admitted)}"
        f" quarantined={len(result.quarantined)} conflicts={len(result.conflicts)}"
        f" released_but_absent={len(result.released_but_absent)}"
        f" quarantine={'accepted' if accepted else 'not accepted'}\n"
    )
    return EXIT_SUCCESS if accepted else EXIT_QUARANTINE_NOT_ACCEPTED


def _build(arguments: argparse.Namespace) -> int:
    # Everything is checked before the first byte is copied.
    spec_path = Path(arguments.spec)
    spec = read_release_spec(spec_path)
    check_release_id_free(Path(arguments.release_records), spec.release_id)
    base = spec_path.parent
    planned = plan_copies(spec, base)
    check_kb_versions(spec, base)
    output = Path(arguments.output)
    inputs = (spec_path, *(base / asset.source for asset in spec.assets))
    with new_output_folder(output, inputs) as staging:
        write_candidate_manifest(staging, spec, copy_files(planned, staging))
    manifest = output / MANIFEST_FILE_NAME
    sys.stdout.write(f"release_id={spec.release_id} files={len(planned)} manifest={manifest}\n")
    return EXIT_SUCCESS


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="supportiq-release")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser(
        "ingest-kb", help="Admit or quarantine the KB document versions of a raw KB folder."
    )
    ingest.add_argument("--kb-folder", required=True, help="data/raw/kb/<kb_version>")
    ingest.add_argument("--intent-labels", required=True, help="contracts/schemas/IntentLabel.yaml")
    ingest.add_argument("--output", required=True, help="A new or empty folder.")
    ingest.add_argument(
        "--accepted-quarantine",
        type=_issue_url,
        help="The URL of the issue that accepted the quarantine (DATA-13).",
    )
    build = commands.add_parser(
        "build-candidate", help="Copy the assets of a spec and write the manifest of a candidate."
    )
    build.add_argument("--spec", required=True, help="A spec in supportiq-release-spec/interim-1.")
    build.add_argument(
        "--release-records", required=True, help="eval/releases: one folder for each release ID."
    )
    build.add_argument("--output", required=True, help="A new or empty folder.")
    add_gate_commands(commands.add_parser)
    add_distribution_commands(commands.add_parser)
    return parser


def _status_of(error: ReleaseCommandError) -> int:
    return next(
        (status for root, status in _STATUS_BY_ROOT_ERROR if isinstance(error, root)),
        EXIT_INPUT_INVALID,
    )


def _issue_url(value: str) -> str:
    if _ISSUE_URL.fullmatch(value) is None:
        message = "expected the URL of a GitHub issue"
        raise argparse.ArgumentTypeError(message)
    return value
