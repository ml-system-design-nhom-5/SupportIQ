"""Each case passes only when every expected field matches both operations, named on mismatch."""

from dataclasses import replace
from http import HTTPStatus

import pytest

from supportiq_release.gate.domain import (
    INTERIM_LABEL,
    Case,
    CaseKind,
    CaseResult,
    CaseSet,
    Expected,
    Failure,
    Injection,
    Observation,
    Response,
    WrittenFor,
    check_case,
    written_for_mismatches,
)
from tests.unit.gate.fakes import (
    ABSTAIN,
    FAILS,
    INTERNAL_ERROR,
    INTERNAL_ERROR_PROBLEM,
    MESSAGE,
    SET_NAME,
)

RELEASE = WrittenFor(
    ai_service_contract="1.0.0",
    model_version="fake-model-1",
    routing_version="fake-routing-1",
    kb_version="v9",
    kb_document_count=0,
)


def _fields(result: CaseResult) -> tuple[str, ...]:
    return tuple(mismatch.field for mismatch in result.mismatches)


def _observed(result: CaseResult) -> dict[str, str]:
    return {mismatch.field: mismatch.observed for mismatch in result.mismatches}


def _case(expected: Expected = ABSTAIN, injection: Injection | None = None) -> Case:
    return Case(
        case_id="fake-case-1",
        esc_rule="ESC-04",
        request={"message": MESSAGE},
        injection=injection,
        depends_on_model=injection is None,
        expected=expected,
    )


def _observation(
    codes: tuple[str, ...] = ("no_valid_document",),
    *,
    recommendation: str = "abstain",
    draft_status: str = "abstained",
    llm_called: bool = False,
) -> Observation:
    routing = {"recommendation": recommendation, "reason_codes": list(codes)}
    return Observation(
        analysis=Response(200, {"routing": routing}),
        draft=Response(
            200,
            {"analysis": {"routing": routing}, "status": draft_status, "reason_codes": list(codes)},
        ),
        llm_called=llm_called,
    )


def _failure_observation(problem_type: str = INTERNAL_ERROR) -> Observation:
    # The Problem Details body of contract 1.0.0, whose `status` member is the HTTP status.
    problem = {**INTERNAL_ERROR_PROBLEM, "type": problem_type}
    return Observation(
        analysis=Response(500, problem), draft=Response(500, problem), llm_called=False
    )


def test_a_case_whose_outcome_matches_passes() -> None:
    result = check_case(_case(), _observation())

    assert result.passed
    assert _fields(result) == ()
    assert (result.case_id, result.esc_rule, result.kind) == (
        "fake-case-1",
        "ESC-04",
        CaseKind.REAL_MODEL,
    )
    assert result.injected_failure is None


def test_a_failure_case_with_500_and_its_problem_type_passes() -> None:
    injection = Injection(intent_distribution=None, failure=Failure.INTENT_MODEL)

    result = check_case(_case(FAILS, injection), _failure_observation())

    assert result.passed
    assert result.kind is CaseKind.INJECTED_FAILURE
    assert result.injected_failure is Failure.INTENT_MODEL


def test_a_failure_case_with_another_problem_type_names_both_operations() -> None:
    result = check_case(_case(FAILS), _failure_observation("urn:supportiq:problem:other"))

    assert _fields(result) == ("createAnalysis.problem_type", "createDraft.problem_type")


def test_a_200_where_a_failure_is_expected_names_the_status_and_the_problem_type() -> None:
    result = check_case(_case(FAILS), _observation())

    assert "createAnalysis.http_status" in _fields(result)
    assert "createDraft.http_status" in _fields(result)
    assert "createAnalysis.problem_type" in _fields(result)


def test_the_status_of_a_problem_is_never_read_as_the_status_of_a_draft() -> None:
    # The first gate run failed both cases of ESC-05 on this (gate-run.json of
    # release-2026-11-18-01): the `status` 500 of the problem was read as `draft_status`.
    result = check_case(_case(FAILS), _failure_observation())

    assert INTERNAL_ERROR_PROBLEM["status"] == HTTPStatus.INTERNAL_SERVER_ERROR
    assert result.passed


def test_a_500_where_an_outcome_is_expected_names_each_field_with_what_was_observed() -> None:
    result = check_case(_case(), _failure_observation())

    assert _observed(result) == {
        "createAnalysis.http_status": "500",
        "createAnalysis.problem_type": INTERNAL_ERROR,
        "createDraft.http_status": "500",
        "createDraft.problem_type": INTERNAL_ERROR,
        "createAnalysis.recommendation": "null",
        "createDraft.recommendation": "null",
        "createDraft.draft_status": "null",
        "createAnalysis.reason_codes": "null",
        "createDraft.reason_codes": "null",
    }


def test_an_observed_value_outside_the_contract_is_shown_as_other_never_as_its_text() -> None:
    routing = {"recommendation": MESSAGE, "reason_codes": ["no_valid_document", MESSAGE]}
    observation = Observation(
        analysis=Response(200, {"routing": routing}),
        draft=Response(
            200, {"analysis": {"routing": routing}, "status": MESSAGE, "reason_codes": []}
        ),
        llm_called=True,
    )

    result = check_case(_case(), observation)

    observed = _observed(result)
    assert observed == {
        "createAnalysis.recommendation": "other",
        "createDraft.recommendation": "other",
        "createDraft.draft_status": "other",
        "createAnalysis.no_other_reason_codes": "no_valid_document,other:1",
        "createDraft.required_reason_codes": "empty",
        "createDraft.no_other_reason_codes": "empty",
        "createDraft.llm_called": "true",
    }
    assert MESSAGE not in "".join(_observed(result).values())


def test_a_problem_type_outside_the_contract_is_shown_as_other() -> None:
    result = check_case(_case(FAILS), _failure_observation(MESSAGE))

    assert tuple(_observed(result).values()) == ("other", "other")


def test_a_200_body_is_never_read_as_a_problem() -> None:
    observation = _observation()
    with_type = replace(
        observation, analysis=Response(200, {**observation.analysis.body, "type": INTERNAL_ERROR})
    )

    assert check_case(_case(), with_type).passed


@pytest.mark.parametrize(
    ("observation", "mismatches"),
    [
        (
            _observation(recommendation="escalate"),
            ("createAnalysis.recommendation", "createDraft.recommendation"),
        ),
        (_observation(draft_status="escalation_recommended"), ("createDraft.draft_status",)),
        (
            _observation(()),
            (
                "createAnalysis.required_reason_codes",
                "createAnalysis.no_other_reason_codes",
                "createDraft.required_reason_codes",
                "createDraft.no_other_reason_codes",
            ),
        ),
        (
            _observation(("no_valid_document", "low_confidence")),
            (
                "createAnalysis.forbidden_reason_codes",
                "createAnalysis.no_other_reason_codes",
                "createDraft.forbidden_reason_codes",
                "createDraft.no_other_reason_codes",
            ),
        ),
        (
            _observation(("no_valid_document", "out_of_scope_intent")),
            ("createAnalysis.no_other_reason_codes", "createDraft.no_other_reason_codes"),
        ),
        (
            _observation(("no_valid_document", "requires_authority")),
            (
                "createAnalysis.no_other_reason_codes",
                "createAnalysis.requires_authority",
                "createDraft.no_other_reason_codes",
                "createDraft.requires_authority",
            ),
        ),
        (_observation(llm_called=True), ("createDraft.llm_called",)),
    ],
)
def test_a_field_that_does_not_match_is_named_with_its_operation(
    observation: Observation, mismatches: tuple[str, ...]
) -> None:
    result = check_case(_case(), observation)

    assert not result.passed
    assert _fields(result) == mismatches


def test_an_expected_authority_is_allowed_besides_the_exact_codes() -> None:
    expected = replace(ABSTAIN, requires_authority=True)

    passed = check_case(_case(expected), _observation(("no_valid_document", "requires_authority")))
    missing = check_case(_case(expected), _observation())

    assert passed.passed
    assert _fields(missing) == (
        "createAnalysis.no_other_reason_codes",
        "createAnalysis.requires_authority",
        "createDraft.no_other_reason_codes",
        "createDraft.requires_authority",
    )


def test_authority_that_is_not_checked_matches_either_way() -> None:
    expected = replace(ABSTAIN, requires_authority=None, no_other_reason_codes=False)

    with_authority = _observation(("no_valid_document", "requires_authority"))

    assert check_case(_case(expected), with_authority).passed
    assert check_case(_case(expected), _observation()).passed


def test_codes_of_the_two_operations_are_checked_apart() -> None:
    observation = replace(
        _observation(),
        draft=Response(
            200,
            {
                "analysis": {"routing": {"recommendation": "abstain"}},
                "status": "abstained",
                "reason_codes": ["no_valid_document", "low_confidence"],
            },
        ),
    )

    result = check_case(_case(), observation)

    assert _fields(result) == (
        "createDraft.forbidden_reason_codes",
        "createDraft.no_other_reason_codes",
    )


def test_a_list_of_codes_that_is_not_a_list_counts_as_missing() -> None:
    observation = replace(
        _observation(),
        analysis=Response(200, {"routing": {"recommendation": "abstain", "reason_codes": "x"}}),
    )

    assert _fields(check_case(_case(), observation)) == ("createAnalysis.reason_codes",)


def test_a_body_that_is_not_nested_as_expected_matches_no_field() -> None:
    observation = replace(_observation(), analysis=Response(200, {"routing": "abstain"}))

    result = check_case(_case(), observation)

    assert _fields(result) == ("createAnalysis.recommendation", "createAnalysis.reason_codes")


def _case_set(label: str = INTERIM_LABEL, written_for: WrittenFor = RELEASE) -> CaseSet:
    return CaseSet(label=label, name=SET_NAME, written_for=written_for, cases=(_case(),))


def test_a_set_written_for_the_release_has_no_mismatch() -> None:
    assert written_for_mismatches(_case_set(), RELEASE) == ()


@pytest.mark.parametrize(
    ("written_for", "field"),
    [
        ({"ai_service_contract": "1.1.0"}, "ai_service_contract"),
        ({"model_version": "fake-model-2"}, "model_version"),
        ({"routing_version": "fake-routing-2"}, "routing_version"),
        ({"kb_version": "v10"}, "kb_version"),
        ({"kb_document_count": 1}, "kb_document_count"),
    ],
)
def test_each_field_of_written_for_that_differs_is_named(
    written_for: dict[str, object], field: str
) -> None:
    case_set = _case_set(written_for=replace(RELEASE, **written_for))

    assert written_for_mismatches(case_set, RELEASE) == (field,)


def test_a_set_without_the_interim_label_is_named() -> None:
    assert written_for_mismatches(_case_set("the shared scenario set"), RELEASE) == ("label",)
