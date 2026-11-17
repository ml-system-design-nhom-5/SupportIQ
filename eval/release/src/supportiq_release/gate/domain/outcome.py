"""The outcome of one run of the offline evaluation gate (DATA-57, ADR-0021).

The gate passes only when every part passes: every escalation case, every check on the
candidate, and both folders of guardrail tests of TEST-26 (ADR-0021, Release and the offline
evaluation gate, statement 3). A guardrail folder passes only when it ran at least one test and
none failed, errored, or was skipped, because a skipped guardrail test is not a pass (TEST-20).
"""

import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum

from supportiq_release.gate.domain.cases import Case
from supportiq_release.gate.domain.checks import CaseResult

# The routes of contract 1.0.0 of `ai-service`: none performs a transaction (TEST-26, FR-06).
CONTRACT_ROUTES = frozenset(
    {
        ("POST", "/v1/analyses"),
        ("POST", "/v1/drafts"),
        ("GET", "/v1/kb-documents/{document_id}/versions/{version}"),
        ("GET", "/v1/asset-versions"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
    }
)
# A placeholder of ADR-0010 (Placeholder syntax), such as `[ORDER_ID_1]` or `[EMAIL]`.
_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z_]*\]|\[[A-Z][A-Z_]*_[1-9][0-9]*\]")
# The known gaps of the first release: ADR-0021 (Release and the offline evaluation gate,
# statement 4), with the fourth gap of ADR-0025.
KNOWN_GAPS = (
    "The acceptance set of main is contaminated (DATA-23), so no quality target is reported"
    " from it.",
    "The shared scenario set of Groups 2 and 5 does not exist yet (CST-02), so interim cases"
    " replace it (ADR-0021, Exception to TEST-26).",
    "The first release serves no KB document (ADR-0021, KB ingestion), so every policy question"
    " leads to abstention (ESC-04).",
    "The routing configuration is not tuned on validation data: its values are those of main"
    " (ADR-0025).",
)
SHARED_SCENARIO_SET_ITEM = (
    "TEST-26, 'Mandatory escalation cases from the shared scenario set are routed correctly':"
    " not met. Interim cases replace the shared scenario set (ADR-0021, Exception to TEST-26)."
)
NO_LLM_CALL = (
    "No LLM call was made: the LLM step of the gate records each call and fails it, and never"
    " calls a provider."
)
# Which parts load the candidate (ADR-0021, Release and the offline evaluation gate, statement
# 3, where a test depends on what the manifest serves).
CANDIDATE_SCOPE = (
    "The escalation cases and the candidate checks run on the application of the candidate,"
    " with its manifest loaded. The guardrail tests do not load it: those of ai-service check"
    " the service token and the packaged egress allow-list, those of backend serve ai-service"
    " from fakes, and no asset of the manifest changes what they check."
)


class GuardrailSuite(StrEnum):
    """A folder of guardrail tests of TEST-26 that the gate runs as it is."""

    AI_SERVICE = "ai_service_guardrails"
    BACKEND = "backend_guardrails"


class CandidateCheck(StrEnum):
    """A check that the gate makes on the application of the candidate itself."""

    ROUTES = "routes_are_those_of_contract_1_0_0"
    NO_CASE_TEXT_IN_LOGS = "no_case_text_in_the_logs"
    NO_LLM_CALL = "no_llm_call"


@dataclass(frozen=True, slots=True)
class GuardrailResult:
    """The result of one folder of guardrail tests.

    Attributes:
        suite: The folder.
        tests: The number of tests that ran.
        failures: The number of tests that failed.
        errors: The number of tests that errored.
        skipped: The number of tests that were skipped.
        test_classnames: The test classes or modules that ran, sorted, each once.
    """

    suite: GuardrailSuite
    tests: int
    failures: int
    errors: int
    skipped: int
    test_classnames: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Whether at least one test ran and every test passed (TEST-20)."""
        return self.tests >= 1 and self.failures == self.errors == self.skipped == 0


@dataclass(frozen=True, slots=True)
class CheckResult:
    """The result of one check on the candidate.

    Attributes:
        check: The check.
        passed: Whether it passed.
    """

    check: CandidateCheck
    passed: bool


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """Every part of one gate run.

    Attributes:
        cases: The result of each escalation case, in the order of the set.
        checks: The checks on the candidate.
        guardrails: The folders of guardrail tests.
        llm_calls: The calls that the LLM step of the gate received during the run.
    """

    cases: tuple[CaseResult, ...]
    checks: tuple[CheckResult, ...]
    guardrails: tuple[GuardrailResult, ...]
    llm_calls: int

    @property
    def passed(self) -> bool:
        """Whether every part ran and passed; a missing part fails the gate."""
        return (
            bool(self.cases)
            and all(result.passed for result in self.cases)
            and {result.check for result in self.checks} == set(CandidateCheck)
            and all(result.passed for result in self.checks)
            and {result.suite for result in self.guardrails} == set(GuardrailSuite)
            and all(result.passed for result in self.guardrails)
        )


def candidate_checks(
    routes: Collection[tuple[str, str]], log_text: str, cases: Iterable[Case], llm_calls: int
) -> tuple[CheckResult, ...]:
    """Check the routes, the logs, and the LLM calls of the candidate.

    Args:
        routes: Each method and path that the application of the candidate serves.
        log_text: Every line that the candidate logged during the run.
        cases: The cases that were sent to it.
        llm_calls: The calls that the LLM step of the gate received.

    Returns:
        The result of each check of `CandidateCheck`.
    """
    leaked = any(_case_text_in(log_text, case) for case in cases)
    return (
        CheckResult(CandidateCheck.ROUTES, frozenset(routes) == CONTRACT_ROUTES),
        CheckResult(CandidateCheck.NO_CASE_TEXT_IN_LOGS, not leaked),
        CheckResult(CandidateCheck.NO_LLM_CALL, llm_calls == 0),
    )


def _case_text_in(log_text: str, case: Case) -> bool:
    # A message and every placeholder in it are Confidential, so neither may be logged (LOG-29).
    message = case.message
    if message and message in log_text:
        return True
    return any(placeholder in log_text for placeholder in _PLACEHOLDER.findall(message))
