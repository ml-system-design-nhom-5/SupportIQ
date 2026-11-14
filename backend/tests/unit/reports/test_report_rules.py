"""The rules of the report: the period, shares, averages, absences, and item order (FR-10)."""

from datetime import datetime, timedelta

import pytest
from hypothesis import given
from hypothesis import strategies as st

from supportiq_backend.reports import (
    AiErrorRate,
    AiOutcomes,
    CodeCount,
    DraftDecisions,
    Escalations,
    InvalidReportPeriodError,
    LlmCost,
    ReportPeriod,
    build_report_period,
    compute_rounded_average,
    compute_share,
    order_code_counts,
)
from supportiq_backend.suggestions import AiReasonCode, PartStatus
from supportiq_backend.tickets import StaffReasonCode
from tests.unit.reports.fakes import END_AT, START_AT

PERIOD_DETAIL = "The parameter start_at must be earlier than end_at."
ONE_MICROSECOND = timedelta(microseconds=1)
NO_DECISIONS = DraftDecisions(0, 0, 0, {}, {})
COUNTS = st.integers(min_value=0, max_value=10_000)
AI_REASON_CODES = tuple(AiReasonCode)
ONE_QUARTER = 0.25
HALF = 0.5


def test_period_keeps_a_start_earlier_than_its_end() -> None:
    period = build_report_period(START_AT, END_AT)

    assert period == ReportPeriod(START_AT, END_AT)


def test_period_one_microsecond_long_is_valid() -> None:
    period = build_report_period(START_AT, START_AT + ONE_MICROSECOND)

    assert period.end_at - period.start_at == ONE_MICROSECOND


@pytest.mark.parametrize("end_at", [START_AT, START_AT - ONE_MICROSECOND], ids=["equal", "earlier"])
def test_period_whose_start_is_not_earlier_than_its_end_is_refused_with_the_example_detail(
    end_at: datetime,
) -> None:
    with pytest.raises(InvalidReportPeriodError) as caught:
        build_report_period(START_AT, end_at)

    assert caught.value.detail == PERIOD_DETAIL


def test_share_is_the_count_divided_by_the_total() -> None:
    share = compute_share(1, 4)

    assert share == ONE_QUARTER


def test_share_of_an_empty_total_is_absent() -> None:
    share = compute_share(0, 0)

    assert share is None


@pytest.mark.parametrize(
    ("total", "count", "average"),
    [(421, 2, 211), (420, 2, 210), (1, 3, 0), (2, 3, 1), (0, 5, 0), (7, 1, 7)],
    ids=["half-up", "exact", "below-half", "above-half", "zero-total", "single"],
)
def test_average_is_rounded_to_the_nearest_integer_with_halves_up(
    total: int, count: int, average: int
) -> None:
    rounded = compute_rounded_average(total, count)

    assert rounded == average


def test_average_without_values_is_absent() -> None:
    rounded = compute_rounded_average(0, 0)

    assert rounded is None


def test_code_counts_follow_the_order_of_the_codes_and_leave_out_zero_counts() -> None:
    count_by_code = {
        StaffReasonCode.OTHER: 2,
        StaffReasonCode.KB_GAP: 0,
        StaffReasonCode.WRONG_INTENT: 1,
    }

    items = order_code_counts(count_by_code, tuple(StaffReasonCode))

    assert items == (
        CodeCount(StaffReasonCode.WRONG_INTENT, 1),
        CodeCount(StaffReasonCode.OTHER, 2),
    )


def test_code_counts_of_nothing_are_empty() -> None:
    items = order_code_counts({}, tuple(StaffReasonCode))

    assert items == ()


def test_draft_decisions_have_a_share_of_each_decision() -> None:
    decisions = DraftDecisions(1, 2, 1, {}, {})

    shares = (decisions.approve_share, decisions.edit_share, decisions.reject_share)

    assert shares == (0.25, 0.5, 0.25)


def test_draft_decisions_without_any_decision_have_no_share() -> None:
    shares = (NO_DECISIONS.approve_share, NO_DECISIONS.edit_share, NO_DECISIONS.reject_share)

    assert shares == (None, None, None)


def test_edits_and_rejections_by_reason_follow_the_order_of_staff_reason_codes() -> None:
    decisions = DraftDecisions(
        0,
        2,
        1,
        {StaffReasonCode.TONE_OR_CLARITY: 1, StaffReasonCode.WRONG_SOURCE: 1},
        {StaffReasonCode.OTHER: 1, StaffReasonCode.KB_GAP: 1},
    )

    by_reason = (decisions.edit_by_reason, decisions.reject_by_reason)

    assert by_reason == (
        (CodeCount(StaffReasonCode.WRONG_SOURCE, 1), CodeCount(StaffReasonCode.TONE_OR_CLARITY, 1)),
        (CodeCount(StaffReasonCode.KB_GAP, 1), CodeCount(StaffReasonCode.OTHER, 1)),
    )


def test_escalations_by_reason_follow_the_order_of_staff_reason_codes() -> None:
    escalations = Escalations(2, {StaffReasonCode.OTHER: 1, StaffReasonCode.CASE_EXCEPTION: 2})

    by_reason = escalations.by_reason

    assert by_reason == (
        CodeCount(StaffReasonCode.CASE_EXCEPTION, 2),
        CodeCount(StaffReasonCode.OTHER, 1),
    )


def test_ai_outcomes_list_completed_statuses_in_contract_order_without_cancelled() -> None:
    outcomes = AiOutcomes(
        {
            PartStatus.UNAVAILABLE: 1,
            PartStatus.CANCELLED: 3,
            PartStatus.ABSTAINED: 2,
            PartStatus.DRAFT_READY: 4,
        },
        {},
    )

    by_status = outcomes.by_draft_status

    assert by_status == (
        CodeCount(PartStatus.DRAFT_READY, 4),
        CodeCount(PartStatus.ABSTAINED, 2),
        CodeCount(PartStatus.UNAVAILABLE, 1),
    )


def test_ai_outcomes_list_reason_codes_in_the_order_of_ai_reason_codes() -> None:
    outcomes = AiOutcomes(
        {},
        {
            AiReasonCode.AI_SERVICE_UNAVAILABLE: 1,
            AiReasonCode.REQUIRES_AUTHORITY: 1,
            AiReasonCode.HUMAN_AGENT_REQUESTED: 1,
        },
    )

    by_code = outcomes.by_reason_code

    assert by_code == (
        CodeCount(AiReasonCode.HUMAN_AGENT_REQUESTED, 1),
        CodeCount(AiReasonCode.REQUIRES_AUTHORITY, 1),
        CodeCount(AiReasonCode.AI_SERVICE_UNAVAILABLE, 1),
    )


def test_error_rate_without_suggestions_has_no_share() -> None:
    rate = AiErrorRate(suggestion_count=0, failed_count=0)

    assert rate.share is None


def test_error_rate_share_is_failed_suggestions_over_all() -> None:
    rate = AiErrorRate(suggestion_count=4, failed_count=1)

    assert rate.share == ONE_QUARTER


def test_llm_cost_without_a_call_has_no_average() -> None:
    cost = LlmCost(total_micro_usd=0, llm_call_count=0)

    assert cost.average_micro_usd is None


@given(approve=st.integers(min_value=1, max_value=10_000), edit=COUNTS, reject=COUNTS)
def test_draft_decision_shares_are_between_zero_and_one_and_add_up_to_one(
    approve: int, edit: int, reject: int
) -> None:
    decisions = DraftDecisions(approve, edit, reject, {}, {})
    approve_share = decisions.approve_share
    edit_share = decisions.edit_share
    reject_share = decisions.reject_share

    assert approve_share is not None
    assert edit_share is not None
    assert reject_share is not None
    assert min(approve_share, edit_share, reject_share) >= 0
    assert max(approve_share, edit_share, reject_share) <= 1
    assert approve_share + edit_share + reject_share == pytest.approx(1)


@given(count_by_code=st.dictionaries(st.sampled_from(AI_REASON_CODES), COUNTS))
def test_ordered_code_counts_keep_the_enum_order_and_only_positive_counts(
    count_by_code: dict[AiReasonCode, int],
) -> None:
    items = order_code_counts(count_by_code, AI_REASON_CODES)
    codes = [item.code for item in items]

    assert codes == sorted(codes, key=AI_REASON_CODES.index)
    assert min((item.count for item in items), default=1) >= 1


@given(total=COUNTS, count=st.integers(min_value=1, max_value=10_000))
def test_rounded_average_is_within_half_of_the_exact_average(total: int, count: int) -> None:
    rounded = compute_rounded_average(total, count)

    assert rounded is not None
    assert abs(rounded - total / count) <= HALF
