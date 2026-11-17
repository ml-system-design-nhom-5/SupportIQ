"""The commands of the offline evaluation gate: `run-gate` and `publish-candidate` (DATA-57).

- `run-gate` checks a candidate, reads the escalation cases and their approval, reads the
  results of both folders of guardrail tests, runs every case on the candidate in this process,
  and writes the record of the run into `eval/releases/<release_id>/`. It exits with status 0
  when every part passed and 1 when one failed; the record is written either way, so the release
  ID is never used again.
- `publish-candidate` copies a candidate whose record passed, with the approved cases as they
  are, into a new release folder, and then links the gate run next to the record.

Both refuse cases whose approval is not frozen or covers other bytes. The gate runs in its
container, without network (`eval/release/README.md`, The offline evaluation gate).

The candidate reads its settings from the environment of the process, as `serve` does. This
module is the one place that sets them, once for each run: a new service token and LLM
settings that no call reads (`gate/adapters/candidate_run.py`).
"""

import argparse
import os
import re
import sys
from collections.abc import Callable
from pathlib import Path

from supportiq_release.composition_root.exit_statuses import EXIT_GATE_FAILED, EXIT_SUCCESS
from supportiq_release.errors import ReleaseCommandError
from supportiq_release.files import new_output_folder
from supportiq_release.gate.adapters import (
    CandidateFacts,
    CandidateRun,
    CasesFile,
    GatePorts,
    GateRunIdentity,
    candidate_settings,
    check_cases_approved,
    link_release,
    new_service_token,
    prepare_release,
    read_candidate_facts,
    read_cases_file,
    read_guardrail_result,
    run_cases,
    write_gate_record,
)
from supportiq_release.gate.domain import (
    GateOutcome,
    GuardrailResult,
    GuardrailSuite,
    candidate_checks,
    check_case,
    written_for_mismatches,
)

type AddParser = Callable[..., argparse.ArgumentParser]

_GIT_COMMIT = re.compile(r"[0-9a-f]{40}")


class CasesNotWrittenForCandidateError(ReleaseCommandError):
    """The escalation cases are written for another release. The message names the fields."""

    def __init__(self, fields: tuple[str, ...]) -> None:
        """Build the error with a message that names the fields that differ.

        Args:
            fields: The fields of `written_for`, or the label, that the candidate does not match.
        """
        super().__init__(
            "The escalation cases are not written for this candidate: " + ", ".join(fields) + "."
        )
        self.fields = fields


def run_gate(arguments: argparse.Namespace) -> int:
    """Run the offline evaluation gate on one candidate, and write the record of the run.

    Args:
        arguments: The arguments of `run-gate`.

    Returns:
        0 when every part of the gate passed, 1 when one failed.
    """
    candidate, cases = _checked_inputs(arguments)
    guardrails = (
        read_guardrail_result(GuardrailSuite.AI_SERVICE, Path(arguments.ai_service_guardrails)),
        read_guardrail_result(GuardrailSuite.BACKEND, Path(arguments.backend_guardrails)),
    )
    outcome = _outcome(cases, _run_candidate(candidate, cases), guardrails)
    identity = GateRunIdentity(
        release_id=candidate.release_id,
        manifest_sha256=candidate.manifest_sha256,
        git_commit=arguments.git_commit,
        case_set=cases.case_set.name,
        cases_sha256=cases.sha256,
    )
    record = write_gate_record(Path(arguments.release_records), identity, outcome)
    failed = sum(not result.passed for result in outcome.cases)
    sys.stdout.write(
        f"release_id={candidate.release_id} cases={len(outcome.cases)} failed_cases={failed}"
        f" outcome={'passed' if outcome.passed else 'failed'} record={record}\n"
    )
    return EXIT_SUCCESS if outcome.passed else EXIT_GATE_FAILED


def publish(arguments: argparse.Namespace) -> int:
    """Publish a candidate whose gate run passed with the approved cases.

    Args:
        arguments: The arguments of `publish-candidate`.

    Returns:
        0 when the release folder is written and linked next to the record.
    """
    candidate = Path(arguments.candidate)
    records = Path(arguments.release_records)
    cases_path = Path(arguments.cases)
    cases = read_cases_file(cases_path)
    check_cases_approved(cases, cases_path)
    output = Path(arguments.output)
    with new_output_folder(output, (candidate, cases_path, records)) as staging:
        release = prepare_release(candidate, records, cases.sha256, staging)
    # Linked only once the release folder is in place, so a failed move leaves no link (ERR-04).
    link_release(records, release)
    sys.stdout.write(f"published={output}\n")
    return EXIT_SUCCESS


def add_gate_commands(add_parser: AddParser) -> None:
    """Add `run-gate` and `publish-candidate` to the command line.

    Args:
        add_parser: `add_parser` of the subcommands of `supportiq-release`.
    """
    gate = add_parser(
        "run-gate", help="Run the offline evaluation gate on a candidate and record the run."
    )
    gate.add_argument("--candidate", required=True, help="The folder of the candidate.")
    gate.add_argument("--cases", required=True, help="eval/suites/escalation/<set>/cases.json")
    gate.add_argument(
        "--ai-service-guardrails",
        required=True,
        help="The JUnit XML of ai-service/tests/integration/guardrails.",
    )
    gate.add_argument(
        "--backend-guardrails",
        required=True,
        help="The JUnit XML of backend/tests/integration/guardrails.",
    )
    gate.add_argument("--git-commit", required=True, type=_git_commit, help="git rev-parse HEAD")
    gate.add_argument("--release-records", required=True, help="eval/releases")
    published = add_parser("publish-candidate", help="Publish a candidate whose gate run passed.")
    published.add_argument("--candidate", required=True, help="The folder of the candidate.")
    published.add_argument("--cases", required=True, help="The cases that the gate ran.")
    published.add_argument("--release-records", required=True, help="eval/releases")
    published.add_argument("--output", required=True, help="A new or empty folder.")


def _checked_inputs(arguments: argparse.Namespace) -> tuple[CandidateFacts, CasesFile]:
    # Everything that stops the run without a record, before the candidate is built.
    candidate = read_candidate_facts(Path(arguments.candidate))
    cases_path = Path(arguments.cases)
    cases = read_cases_file(cases_path)
    check_cases_approved(cases, cases_path)
    mismatches = written_for_mismatches(cases.case_set, candidate.release)
    if mismatches:
        raise CasesNotWrittenForCandidateError(mismatches)
    return candidate, cases


def _run_candidate(candidate: CandidateFacts, cases: CasesFile) -> CandidateRun:
    # The settings that the candidate reads from the environment, set here and nowhere else.
    service_token = new_service_token()
    os.environ.update(candidate_settings(service_token))
    return run_cases(candidate.manifest_path, cases.case_set.cases, GatePorts(), service_token)


def _outcome(
    cases: CasesFile, run: CandidateRun, guardrails: tuple[GuardrailResult, ...]
) -> GateOutcome:
    results = zip(cases.case_set.cases, run.observations, strict=True)
    return GateOutcome(
        cases=tuple(check_case(case, observation) for case, observation in results),
        checks=candidate_checks(run.routes, run.log_text, cases.case_set.cases, run.llm_calls),
        guardrails=guardrails,
        llm_calls=run.llm_calls,
    )


def _git_commit(value: str) -> str:
    if _GIT_COMMIT.fullmatch(value) is None:
        message = "expected the 40 hexadecimal characters of a commit"
        raise argparse.ArgumentTypeError(message)
    return value
