"""The outcome of one run of the offline evaluation gate (DATA-57, ADR-0021).

The gate passes only when every part passes: every escalation case, every check on the
candidate, and both folders of guardrail tests of TEST-26 (ADR-0021, Release and the offline
evaluation gate, statement 3). A guardrail folder passes only when it ran at least one test and
none failed, errored, or was skipped, because a skipped guardrail test is not a pass (TEST-20).
"""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import StrEnum

from supportiq_release.gate.domain.cases import Case
from supportiq_release.gate.domain.checks import CaseResult, Observation

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
# The known gaps of a release: ADR-0021 (Release and the offline evaluation gate, statement 4),
# with the gap of ADR-0025, and, once the KB serves documents, those of the design of the gate
# for a release with KB documents (DATA-57 item 2, Untuned values).
_CONTAMINATED_SET = (
    "The acceptance set of main is contaminated (DATA-23), so no quality target is reported"
    " from it."
)
_NO_SHARED_SET = (
    "The shared scenario set of Groups 2 and 5 does not exist yet (CST-02), so interim cases"
    " replace it (ADR-0021, Exception to TEST-26)."
)
_NO_KB_DOCUMENT = (
    "The first release serves no KB document (ADR-0021, KB ingestion), so every policy question"
    " leads to abstention (ESC-04)."
)
_UNTUNED_ROUTING = (
    "The routing configuration is not tuned on validation data: its values are those of main"
    " (ADR-0025)."
)
_UNTUNED_INDEX = (
    "The minimum similarity of the index is not tuned on validation data: its value is that of"
    " main (ADR-0027)."
)
_FIRST_BASELINE = (
    "Retrieval (NFR-03) and grounding (NFR-04) are not measured by the gate; they are measured"
    " outside it, and the first measurement is a baseline (DATA-48)."
)
KNOWN_GAPS = (_CONTAMINATED_SET, _NO_SHARED_SET, _NO_KB_DOCUMENT, _UNTUNED_ROUTING)
KNOWN_GAPS_WITH_KB_DOCUMENTS = (
    _CONTAMINATED_SET,
    _NO_SHARED_SET,
    _UNTUNED_ROUTING,
    _UNTUNED_INDEX,
    _FIRST_BASELINE,
)
SHARED_SCENARIO_SET_ITEM = (
    "TEST-26, 'Mandatory escalation cases from the shared scenario set are routed correctly':"
    " not met. Interim cases replace the shared scenario set (ADR-0021, Exception to TEST-26)."
)
NO_LLM_CALL = (
    "No LLM call was made: the LLM step of the gate records each call and fails it, and never"
    " calls a provider."
)
LLM_CALLS_AS_EXPECTED = (
    "The LLM step of the gate received one call for each case that expects a draft and no other"
    " call. It records each call and fails it, and never calls a provider."
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
    LLM_CALLS_AS_EXPECTED = "llm_calls_as_expected"


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
        observed: What made it fail, never text of a case: each route outside contract 1.0.0
            as `+<method> <path>` and each missing route as `-<method> <path>`, the IDs of the
            cases whose text was logged, or the IDs of the cases whose LLM call differs from
            what they expect, with `calls:<number>` when the total differs; none when it passed.
    """

    check: CandidateCheck
    observed: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        """Whether nothing made the check fail."""
        return not self.observed


@dataclass(frozen=True, slots=True)
class GateOutcome:
    """Every part of one gate run.

    Attributes:
        cases: The result of each escalation case, in the order of the set.
        checks: The checks on the candidate.
        guardrails: The folders of guardrail tests.
        llm_calls: The calls that the LLM step of the gate received during the run.
        known_gaps: The known gaps of the candidate (`known_gaps`).
    """

    cases: tuple[CaseResult, ...]
    checks: tuple[CheckResult, ...]
    guardrails: tuple[GuardrailResult, ...]
    llm_calls: int
    known_gaps: tuple[str, ...] = KNOWN_GAPS

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


def known_gaps(kb_document_count: int) -> tuple[str, ...]:
    """Return the known gaps that the record of a gate run states for a candidate.

    Args:
        kb_document_count: The number of document versions in the KB of the candidate.

    Returns:
        The gaps of the first release while the KB serves no document, and otherwise those of
        a release that serves KB documents.
    """
    return KNOWN_GAPS if kb_document_count == 0 else KNOWN_GAPS_WITH_KB_DOCUMENTS


def candidate_checks(
    routes: Collection[tuple[str, str]],
    log_text: str,
    cases: Sequence[Case],
    observations: Sequence[Observation],
    llm_calls: int,
) -> tuple[CheckResult, ...]:
    """Check the routes, the logs, and the LLM calls of the candidate.

    Args:
        routes: Each method and path that the application of the candidate serves.
        log_text: Every line that the candidate logged during the run.
        cases: The cases that were sent to it, in their order.
        observations: What the candidate did for each case, in the same order.
        llm_calls: The calls that the LLM step of the gate received during the whole run.

    Returns:
        The result of each check of `CandidateCheck`.
    """
    served = frozenset(routes)
    route_differences = (
        *sorted(f"+{method} {path}" for method, path in served - CONTRACT_ROUTES),
        *sorted(f"-{method} {path}" for method, path in CONTRACT_ROUTES - served),
    )
    leaked = tuple(case.case_id for case in cases if _case_text_in(log_text, case))
    return (
        CheckResult(CandidateCheck.ROUTES, route_differences),
        CheckResult(CandidateCheck.NO_CASE_TEXT_IN_LOGS, leaked),
        CheckResult(
            CandidateCheck.LLM_CALLS_AS_EXPECTED, _unexpected_calls(cases, observations, llm_calls)
        ),
    )


def _unexpected_calls(
    cases: Sequence[Case], observations: Sequence[Observation], llm_calls: int
) -> tuple[str, ...]:
    # Each case that expects a draft makes one call and no other case calls, so the total is the
    # number of those cases: a second call in a case, or one outside every case, shows there.
    pairs = tuple(zip(cases, observations, strict=True))
    differing = tuple(
        case.case_id
        for case, observation in pairs
        if observation.llm_called != case.expected.llm_called
    )
    expected_calls = sum(1 for case, _observation in pairs if case.expected.llm_called)
    total = (f"calls:{llm_calls}",) if llm_calls != expected_calls else ()
    return (*differing, *total)


def _case_text_in(log_text: str, case: Case) -> bool:
    # A message and every placeholder in it are Confidential, so neither may be logged (LOG-29).
    message = case.message
    if message and message in log_text:
        return True
    return any(placeholder in log_text for placeholder in _PLACEHOLDER.findall(message))
