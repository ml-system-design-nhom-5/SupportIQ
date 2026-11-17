"""The gate passes only when every part ran and passed; a skipped guardrail test is no pass."""

from dataclasses import replace

import pytest

from supportiq_release.gate.domain import (
    CONTRACT_ROUTES,
    CandidateCheck,
    Case,
    CaseKind,
    CaseResult,
    CheckResult,
    GateOutcome,
    GuardrailResult,
    GuardrailSuite,
    candidate_checks,
)
from tests.unit.gate.fakes import ABSTAIN

MESSAGE = "Where is [ORDER_ID_1] now? It left on Monday."
CASE = Case(
    case_id="fake-case-1",
    esc_rule="ESC-04",
    request={"message": MESSAGE},
    injection=None,
    depends_on_model=True,
    expected=ABSTAIN,
)
PASSED_CASE = CaseResult("fake-case-1", "ESC-04", CaseKind.REAL_MODEL, None, ())
FAILED_CASE = CaseResult("fake-case-2", "ESC-04", CaseKind.REAL_MODEL, None, ("createDraft.x",))
PASSED_CHECKS = tuple(CheckResult(check, passed=True) for check in CandidateCheck)
PASSED_GUARDRAILS = tuple(GuardrailResult(suite, 5, 0, 0, 0) for suite in GuardrailSuite)


def _outcome(**parts: object) -> GateOutcome:
    passing = GateOutcome(
        cases=(PASSED_CASE,), checks=PASSED_CHECKS, guardrails=PASSED_GUARDRAILS, llm_calls=0
    )
    return replace(passing, **parts)


@pytest.mark.parametrize(
    ("counts", "passed"),
    [
        ((1, 0, 0, 0), True),
        ((0, 0, 0, 0), False),
        ((3, 1, 0, 0), False),
        ((3, 0, 1, 0), False),
        ((3, 0, 0, 1), False),
    ],
)
def test_a_guardrail_folder_passes_only_when_a_test_ran_and_none_failed_errored_or_skipped(
    counts: tuple[int, int, int, int], passed: bool
) -> None:
    tests, failures, errors, skipped = counts

    result = GuardrailResult(GuardrailSuite.BACKEND, tests, failures, errors, skipped)

    assert result.passed is passed


def test_a_gate_whose_every_part_passed_passes() -> None:
    assert _outcome().passed


@pytest.mark.parametrize(
    "parts",
    [
        {"cases": ()},
        {"cases": (PASSED_CASE, FAILED_CASE)},
        {"checks": PASSED_CHECKS[1:]},
        {"checks": (CheckResult(CandidateCheck.ROUTES, passed=False), *PASSED_CHECKS[1:])},
        {"guardrails": PASSED_GUARDRAILS[1:]},
        {
            "guardrails": (
                *PASSED_GUARDRAILS[:1],
                GuardrailResult(GuardrailSuite.BACKEND, 5, 0, 0, 1),
            )
        },
    ],
    ids=[
        "no case",
        "a failed case",
        "a missing check",
        "a failed check",
        "a missing guardrail folder",
        "a skipped guardrail test",
    ],
)
def test_a_gate_with_a_missing_or_failed_part_fails(parts: dict[str, object]) -> None:
    assert not _outcome(**parts).passed


def test_the_routes_of_contract_1_0_0_and_clean_logs_pass_every_check() -> None:
    results = candidate_checks(CONTRACT_ROUTES, '{"event": "analysis_created"}\n', [CASE], 0)

    assert results == PASSED_CHECKS


@pytest.mark.parametrize(
    "routes",
    [
        CONTRACT_ROUTES | {("POST", "/v1/refunds")},
        CONTRACT_ROUTES - {("GET", "/health/ready")},
        CONTRACT_ROUTES - {("POST", "/v1/drafts")} | {("PUT", "/v1/drafts")},
    ],
    ids=["an extra route", "a missing route", "another method"],
)
def test_routes_other_than_those_of_contract_1_0_0_fail_the_route_check(
    routes: frozenset[tuple[str, str]],
) -> None:
    results = candidate_checks(routes, "", [CASE], 0)

    assert results[0] == CheckResult(CandidateCheck.ROUTES, passed=False)
    assert all(result.passed for result in results[1:])


@pytest.mark.parametrize(
    "log_text",
    [
        f'{{"event": "x", "message": "{MESSAGE}"}}\n',
        '{"event": "x", "detail": "[ORDER_ID_1]"}\n',
    ],
    ids=["the message", "a placeholder of the message"],
)
def test_a_log_that_holds_text_of_a_case_fails_the_log_check(log_text: str) -> None:
    results = candidate_checks(CONTRACT_ROUTES, log_text, [CASE], 0)

    assert CheckResult(CandidateCheck.NO_CASE_TEXT_IN_LOGS, passed=False) in results


def test_a_placeholder_that_is_not_in_any_message_may_be_logged() -> None:
    results = candidate_checks(CONTRACT_ROUTES, '{"detail": "[EMAIL]"}\n', [CASE], 0)

    assert results == PASSED_CHECKS


def test_a_case_without_a_message_never_matches_an_empty_log() -> None:
    case = replace(CASE, request={"as_of": "2026-11-17T09:00:00Z"})

    assert candidate_checks(CONTRACT_ROUTES, "", [case], 0) == PASSED_CHECKS


def test_one_llm_call_fails_the_llm_check() -> None:
    results = candidate_checks(CONTRACT_ROUTES, "", [CASE], 1)

    assert results[2] == CheckResult(CandidateCheck.NO_LLM_CALL, passed=False)
