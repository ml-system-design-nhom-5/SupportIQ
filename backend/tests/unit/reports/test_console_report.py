"""`getConsoleReport` with fakes of every port: managers only, one read, one event (SEC-16)."""

import pytest

from supportiq_backend.accounts import ForbiddenRoleError, Principal
from supportiq_backend.platform import BackendError, DatabaseUnavailableError, EventName, SpanName
from supportiq_backend.reports import ConsoleReport, TicketCounts
from tests.unit.reports.fakes import (
    AI_OUTCOMES,
    CLOSED,
    CREATED,
    DRAFT_DECISIONS,
    ERROR_RATE,
    ESCALATIONS,
    HANDLING_TIME,
    LATENCY,
    LLM_COST,
    PERIOD,
    build_report_harness,
)
from tests.unit.tickets.console_fakes import (
    ADMIN,
    CUSTOMER,
    MANAGER,
    SIGNED_IN_MANAGER,
    SIGNED_IN_STAFF,
)

pytestmark = pytest.mark.anyio

REFUSED_CALLERS = [(SIGNED_IN_STAFF, "staff"), (ADMIN, "admin"), (CUSTOMER, "customer")]
FIGURE_COUNT_BY_PORT = 4


def test_report_allows_a_manager() -> None:
    harness = build_report_harness()

    manager = harness.use_case.authorize(SIGNED_IN_MANAGER)

    assert manager == MANAGER


@pytest.mark.parametrize(("principal", "role"), REFUSED_CALLERS, ids=["staff", "admin", "customer"])
def test_report_refuses_staff_admins_and_customers_and_records_it(
    principal: Principal, role: str
) -> None:
    harness = build_report_harness()

    with pytest.raises(ForbiddenRoleError):
        harness.use_case.authorize(principal)

    (denied,) = harness.events.of(EventName.PERMISSION_DENIED)
    assert denied.attributes == {
        "account_id": principal.account_id,
        "role": role,
        "operation_id": "getConsoleReport",
    }
    assert harness.transactions.rollback_count == 0


async def test_report_holds_every_figure_of_the_stores_for_the_period() -> None:
    harness = build_report_harness()

    report = await harness.use_case.execute(MANAGER, PERIOD)

    assert report == ConsoleReport(
        period=PERIOD,
        ticket_counts=TicketCounts(created=CREATED, closed=CLOSED),
        draft_decisions=DRAFT_DECISIONS,
        escalations=ESCALATIONS,
        ai_outcomes=AI_OUTCOMES,
        end_to_end_latency=LATENCY,
        ai_error_rate=ERROR_RATE,
        llm_cost=LLM_COST,
        handling_time=HANDLING_TIME,
    )


async def test_report_reads_every_figure_of_the_period_in_one_transaction() -> None:
    harness = build_report_harness()

    await harness.use_case.execute(MANAGER, PERIOD)

    assert harness.tickets.periods == [PERIOD] * FIGURE_COUNT_BY_PORT
    assert harness.ai.periods == [PERIOD] * FIGURE_COUNT_BY_PORT
    assert (harness.transactions.commit_count, harness.transactions.rollback_count) == (0, 1)


async def test_report_runs_in_its_span_and_records_that_it_was_built() -> None:
    harness = build_report_harness()

    await harness.use_case.execute(MANAGER, PERIOD)

    assert harness.steps.steps == [SpanName.BUILD_REPORT]
    (built,) = harness.events.of(EventName.REPORT_BUILT)
    assert built.attributes == {"account_id": MANAGER.account_id}


async def test_report_without_the_database_fails_and_records_no_success() -> None:
    harness = build_report_harness(begin_failure=DatabaseUnavailableError())

    with pytest.raises(DatabaseUnavailableError):
        await harness.use_case.execute(MANAGER, PERIOD)

    assert harness.events.names() == ()


@pytest.mark.parametrize(
    ("tickets_failure", "ai_failure"),
    [(DatabaseUnavailableError(), None), (None, DatabaseUnavailableError())],
    ids=["ticket-figures", "ai-figures"],
)
async def test_report_whose_read_fails_in_the_transaction_rolls_back_and_records_no_success(
    tickets_failure: BackendError | None, ai_failure: BackendError | None
) -> None:
    harness = build_report_harness(tickets_failure=tickets_failure, ai_failure=ai_failure)

    with pytest.raises(DatabaseUnavailableError):
        await harness.use_case.execute(MANAGER, PERIOD)

    assert (harness.transactions.commit_count, harness.transactions.rollback_count) == (0, 1)
    assert harness.events.names() == ()
