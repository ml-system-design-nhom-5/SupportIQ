"""Ports of reports: the figures of a period and the decision records (PY-15, ARCH-26).

Every figure comes from one read-only aggregate in PostgreSQL over the period, never from
telemetry (LOG-33) and never from rows loaded into memory. No method reads a text column or
the pseudonym map; only `DecisionRecordSource` reads the stored, pseudonymized AI exchange.
"""

from typing import Protocol

from supportiq_backend.reports.domain.decision_records import DecisionRecord
from supportiq_backend.reports.domain.report import (
    AiErrorRate,
    AiOutcomes,
    DraftDecisions,
    EndToEndLatency,
    Escalations,
    HandlingTime,
    LlmCost,
    ReportPeriod,
    TicketCounts,
)


class TicketFigures(Protocol):
    """Count the tickets of a period and what staff and managers did with them."""

    async def load_ticket_counts(self, period: ReportPeriod) -> TicketCounts:
        """Count the tickets created and the tickets closed in the period, by handling mode.

        Args:
            period: The period.

        Returns:
            The counts.
        """
        ...

    async def load_handling_time(self, period: ReportPeriod) -> HandlingTime:
        """Measure the median handling time of the tickets closed in the period, by mode.

        Args:
            period: The period.

        Returns:
            The handling time of each mode.
        """
        ...

    async def load_draft_decisions(self, period: ReportPeriod) -> DraftDecisions:
        """Count the `approve`, `edit`, and `reject` decisions of the period.

        Args:
            period: The period.

        Returns:
            The counts, overall and by staff reason code.
        """
        ...

    async def load_escalations(self, period: ReportPeriod) -> Escalations:
        """Count the escalations of the period.

        Args:
            period: The period.

        Returns:
            The counts, overall and by staff reason code.
        """
        ...


class AiFigures(Protocol):
    """Count and measure the AI parts completed in a period."""

    async def load_ai_outcomes(self, period: ReportPeriod) -> AiOutcomes:
        """Count the draft parts completed in the period, without `cancelled` parts.

        Args:
            period: The period.

        Returns:
            The counts by status and by AI reason code.
        """
        ...

    async def load_end_to_end_latency(self, period: ReportPeriod) -> EndToEndLatency:
        """Measure the latency of the first draft of each ticket, for those completed in it.

        Args:
            period: The period.

        Returns:
            The number of tickets and the percentiles.
        """
        ...

    async def load_ai_error_rate(self, period: ReportPeriod) -> AiErrorRate:
        """Count the suggestions completed in the period, and those that failed.

        Args:
            period: The period.

        Returns:
            The counts.
        """
        ...

    async def load_llm_cost(self, period: ReportPeriod) -> LlmCost:
        """Sum the LLM cost of the draft parts completed in the period.

        Args:
            period: The period.

        Returns:
            The total and the number of LLM calls.
        """
        ...


class DecisionRecordSource(Protocol):
    """Read the decision records of a period."""

    async def load_decision_records(self, period: ReportPeriod) -> tuple[DecisionRecord, ...]:
        """Load one record per ticket closed or escalated in the period.

        Args:
            period: The period.

        Returns:
            The records, in the order of the ticket numbers.
        """
        ...


class DecisionRecordFile(Protocol):
    """Keep the decision records of an export in its output file."""

    async def save_decision_records(self, records: tuple[DecisionRecord, ...]) -> None:
        """Write the records as one JSON object per line, replacing the file.

        Args:
            records: The records.

        Raises:
            ExportWriteFailedError: The file could not be written.
        """
        ...
