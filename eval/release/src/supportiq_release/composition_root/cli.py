"""The command line of the release command: `supportiq-release <command>` (ARCH-21).

- `ingest-kb` reads a raw KB folder and writes the KB, the document-to-intent mapping, and the
  report of the ingestion (ADR-0021, KB ingestion). A run that quarantines a record, or finds
  a released version missing from the KB file, fails until an issue accepts it (DATA-13): it
  still writes its files, and it exits with status 3 unless `--accepted-quarantine` names
  that issue.
- `build-candidate` copies the six assets that a spec names into a new folder, writes the
  manifest of a candidate, and checks it as `ai-service` checks a release (ADR-0021, Release
  and the offline evaluation gate). The candidate has no gate run, so no replica serves it.

Every expected failure is an error of the root `ReleaseCommandError` or a `ReleaseInvalidError`
of `ai-service`: the command prints its message and exits with status 2, and the output folder
is left as it was. Nothing that the command prints holds text of the KB.
"""

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from supportiq_ai_service.release.manifest import ReleaseInvalidError

from supportiq_release.candidate.adapters import (
    check_kb_versions,
    check_release_id_free,
    copy_files,
    plan_copies,
    read_release_spec,
    write_candidate_manifest,
)
from supportiq_release.candidate.domain import MANIFEST_FILE_NAME
from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import new_output_folder
from supportiq_release.kb_ingestion.adapters import (
    content_sha256,
    read_intent_labels,
    read_raw_kb_folder,
    write_ingestion,
)
from supportiq_release.kb_ingestion.domain import admit

EXIT_SUCCESS = 0
EXIT_INPUT_INVALID = 2
EXIT_QUARANTINE_NOT_ACCEPTED = 3
_ISSUE_URL = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*")


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command of the release command.

    Args:
        argv: The arguments after the program name; the process arguments when None.

    Returns:
        The exit status: 0 when the command succeeded, 2 for an input that cannot be used or
        a candidate that `ai-service` refuses, and 3 when quarantined records wait for an
        issue that accepts them.
    """
    arguments = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    try:
        return _ingest_kb(arguments) if arguments.command == "ingest-kb" else _build(arguments)
    except ReleaseCommandError as error:
        sys.stderr.write(f"{error}\n")
    except ReleaseInvalidError as error:
        # The reason, the asset, and the path inside the release, never the content of a file.
        where = "".join(
            f" {name}={value}"
            for name, value in (("asset", error.asset), ("file", error.file_path))
            if value is not None
        )
        sys.stderr.write(f"{error}{where}\n")
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
    return parser


def _issue_url(value: str) -> str:
    if _ISSUE_URL.fullmatch(value) is None:
        message = "expected the URL of a GitHub issue"
        raise argparse.ArgumentTypeError(message)
    return value
