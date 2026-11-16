"""`getConsoleReport`: the report of a period, for managers only (FR-10, ADR-0012).

The role check runs first, in the application layer (SEC-16): staff, admins, and customers get
`403` before the period is even parsed. The report is built in one read transaction, from
`backend` records only (LOG-33).
"""

from dataclasses import dataclass

from supportiq_backend.accounts import Authorizer, Principal, SupportPrincipal
from supportiq_backend.platform import (
    EventName,
    EventRecorder,
    OperationId,
    SpanName,
    StepTracer,
    TransactionRunner,
)
from supportiq_backend.reports.domain import (
    AiFigures,
    ConsoleReport,
    ReportPeriod,
    TicketFigures,
)


@dataclass(frozen=True, slots=True)
class ReportStores:
    """The stores of the report, all in one transaction.

    Attributes:
        tickets: The figures of tickets, decisions, and escalations.
        ai: The figures of the AI parts.
    """

    tickets: TicketFigures
    ai: AiFigures


@dataclass(frozen=True, slots=True)
class ReportPorts:
    """The ports of the report besides its stores.

    Attributes:
        authorizer: The role check.
        events: Where `report.built` is recorded.
        steps: Runs the build in the span `build_report`.
    """

    authorizer: Authorizer
    events: EventRecorder
    steps: StepTracer


class GetConsoleReport:
    """Build the report of one period (`getConsoleReport`). It changes nothing."""

    def __init__(self, transactions: TransactionRunner[ReportStores], ports: ReportPorts) -> None:
        """Keep the dependencies.

        Args:
            transactions: Opens the read transaction.
            ports: The ports.
        """
        self._transactions = transactions
        self._ports = ports

    def authorize(self, principal: Principal) -> SupportPrincipal:
        """Allow only managers, before the request is parsed.

        Args:
            principal: The caller.

        Returns:
            The caller as a manager.

        Raises:
            ForbiddenRoleError: The caller is not a manager.
        """
        return self._ports.authorizer.require_manager(principal, OperationId.GET_CONSOLE_REPORT)

    async def execute(self, manager: SupportPrincipal, period: ReportPeriod) -> ConsoleReport:
        """Build the report, one aggregate query per figure.

        Args:
            manager: The caller, from `authorize`.
            period: The period.

        Returns:
            The report.

        Raises:
            DatabaseUnavailableError: The database is not available or a timeout fired.
        """
        with self._ports.steps.step(SpanName.BUILD_REPORT):
            async with self._transactions.begin() as transaction:
                report = await _load_report(transaction.stores, period)
        self._ports.events.record(EventName.REPORT_BUILT, account_id=manager.account_id)
        return report


async def _load_report(stores: ReportStores, period: ReportPeriod) -> ConsoleReport:
    return ConsoleReport(
        period=period,
        ticket_counts=await stores.tickets.load_ticket_counts(period),
        draft_decisions=await stores.tickets.load_draft_decisions(period),
        escalations=await stores.tickets.load_escalations(period),
        ai_outcomes=await stores.ai.load_ai_outcomes(period),
        end_to_end_latency=await stores.ai.load_end_to_end_latency(period),
        ai_error_rate=await stores.ai.load_ai_error_rate(period),
        llm_cost=await stores.ai.load_llm_cost(period),
        handling_time=await stores.tickets.load_handling_time(period),
    )
