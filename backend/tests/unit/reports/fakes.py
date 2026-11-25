"""In-memory fakes of the ports of reports and builders of their figures (ARCH-27, TEST-05)."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.accounts import Authorizer
from app.platform import BackendError
from app.reports import (
    AiErrorRate,
    AiOutcomes,
    DecisionRecord,
    DraftDecisions,
    EndToEndLatency,
    Escalations,
    ExportDecisions,
    ExportStores,
    GetConsoleReport,
    HandlingTime,
    LatencyPercentiles,
    LlmCost,
    ModeCounts,
    ModeHandlingTime,
    ReportPeriod,
    ReportPorts,
    ReportStores,
    TicketCounts,
    build_report_period,
)
from app.suggestions import AiReasonCode, PartStatus
from app.tickets import HandlingMode, StaffReasonCode, TicketId
from tests.unit.platform.fakes import (
    FakeTransactionRunner,
    RecordingEventRecorder,
    RecordingStepTracer,
)

START_AT = datetime(2026, 11, 2, tzinfo=UTC)
END_AT = datetime(2026, 11, 9, tzinfo=UTC)
PERIOD = build_report_period(START_AT, END_AT)
CREATED = ModeCounts(assisted_count=5, manual_count=1)
CLOSED = ModeCounts(assisted_count=2, manual_count=0)
DRAFT_DECISIONS = DraftDecisions(
    approve_count=1,
    edit_count=2,
    reject_count=1,
    edit_count_by_reason={StaffReasonCode.TONE_OR_CLARITY: 1, StaffReasonCode.WRONG_SOURCE: 1},
    reject_count_by_reason={StaffReasonCode.KB_GAP: 1},
)
ESCALATIONS = Escalations(escalation_count=1, count_by_reason={StaffReasonCode.OTHER: 1})
AI_OUTCOMES = AiOutcomes(
    count_by_draft_status={PartStatus.UNAVAILABLE: 1, PartStatus.DRAFT_READY: 2},
    count_by_reason_code={AiReasonCode.AI_SERVICE_UNAVAILABLE: 1},
)
LATENCY = EndToEndLatency(ticket_count=4, percentiles=LatencyPercentiles(3_600, 9_800))
ERROR_RATE = AiErrorRate(suggestion_count=4, failed_count=1)
LLM_COST = LlmCost(total_micro_usd=420, llm_call_count=2)
HANDLING_TIME = HandlingTime(
    assisted=ModeHandlingTime(ticket_count=2, p50_ms=1_050_000),
    manual=ModeHandlingTime(ticket_count=0, p50_ms=None),
)
RECORD = DecisionRecord(
    ticket_id=TicketId("TCK-1"),
    handling_mode=HandlingMode.MANUAL,
    study_pair_id=None,
    study_batch=None,
    created_at=START_AT,
    handling_started_at=None,
    escalated_at=None,
    closed_at=END_AT,
    handling_time_ms=None,
    suggestion=None,
    decisions=(),
)


@dataclass(slots=True)
class _RecordingLoads:
    """Keep the periods asked for, and raise a chosen failure on every load."""

    periods: list[ReportPeriod] = field(default_factory=list[ReportPeriod])
    load_failure: BackendError | None = None

    def _load(self, period: ReportPeriod) -> None:
        self.periods.append(period)
        if self.load_failure is not None:
            raise self.load_failure


@dataclass(slots=True)
class FakeTicketFigures(_RecordingLoads):
    """Return fixed ticket figures, or raise `load_failure`."""

    async def load_ticket_counts(self, period: ReportPeriod) -> TicketCounts:
        """Return `CREATED` and `CLOSED`."""
        self._load(period)
        return TicketCounts(created=CREATED, closed=CLOSED)

    async def load_handling_time(self, period: ReportPeriod) -> HandlingTime:
        """Return `HANDLING_TIME`."""
        self._load(period)
        return HANDLING_TIME

    async def load_draft_decisions(self, period: ReportPeriod) -> DraftDecisions:
        """Return `DRAFT_DECISIONS`."""
        self._load(period)
        return DRAFT_DECISIONS

    async def load_escalations(self, period: ReportPeriod) -> Escalations:
        """Return `ESCALATIONS`."""
        self._load(period)
        return ESCALATIONS


@dataclass(slots=True)
class FakeAiFigures(_RecordingLoads):
    """Return fixed AI figures, or raise `load_failure`."""

    async def load_ai_outcomes(self, period: ReportPeriod) -> AiOutcomes:
        """Return `AI_OUTCOMES`."""
        self._load(period)
        return AI_OUTCOMES

    async def load_end_to_end_latency(self, period: ReportPeriod) -> EndToEndLatency:
        """Return `LATENCY`."""
        self._load(period)
        return LATENCY

    async def load_ai_error_rate(self, period: ReportPeriod) -> AiErrorRate:
        """Return `ERROR_RATE`."""
        self._load(period)
        return ERROR_RATE

    async def load_llm_cost(self, period: ReportPeriod) -> LlmCost:
        """Return `LLM_COST`."""
        self._load(period)
        return LLM_COST


@dataclass(slots=True)
class FakeDecisionRecordSource(_RecordingLoads):
    """Return fixed decision records, or raise `load_failure`."""

    records: tuple[DecisionRecord, ...] = (RECORD,)

    async def load_decision_records(self, period: ReportPeriod) -> tuple[DecisionRecord, ...]:
        """Return `records`."""
        self._load(period)
        return self.records


@dataclass(slots=True)
class RecordingDecisionRecordFile:
    """Keep every batch of records saved, or raise a chosen failure."""

    failure: BackendError | None = None
    saved: list[tuple[DecisionRecord, ...]] = field(
        default_factory=list[tuple[DecisionRecord, ...]]
    )

    async def save_decision_records(self, records: tuple[DecisionRecord, ...]) -> None:
        """Keep the records, or raise `failure`."""
        if self.failure is not None:
            raise self.failure
        self.saved.append(records)


@dataclass(frozen=True, slots=True)
class ReportHarness:
    """The use case of the report on fakes, with what the tests observe."""

    use_case: GetConsoleReport
    tickets: FakeTicketFigures
    ai: FakeAiFigures
    transactions: FakeTransactionRunner[ReportStores]
    events: RecordingEventRecorder
    steps: RecordingStepTracer


@dataclass(frozen=True, slots=True)
class ExportHarness:
    """The use case of the export on fakes, with what the tests observe."""

    use_case: ExportDecisions
    source: FakeDecisionRecordSource
    destination: RecordingDecisionRecordFile
    transactions: FakeTransactionRunner[ExportStores]
    events: RecordingEventRecorder


def build_report_harness(
    *,
    begin_failure: BackendError | None = None,
    tickets_failure: BackendError | None = None,
    ai_failure: BackendError | None = None,
) -> ReportHarness:
    tickets = FakeTicketFigures(load_failure=tickets_failure)
    ai = FakeAiFigures(load_failure=ai_failure)
    events = RecordingEventRecorder()
    steps = RecordingStepTracer()
    transactions = FakeTransactionRunner(
        ReportStores(tickets=tickets, ai=ai), begin_failure=begin_failure
    )
    ports = ReportPorts(authorizer=Authorizer(events), events=events, steps=steps)
    return ReportHarness(
        GetConsoleReport(transactions, ports), tickets, ai, transactions, events, steps
    )


def build_export_harness(
    *,
    begin_failure: BackendError | None = None,
    load_failure: BackendError | None = None,
    destination: RecordingDecisionRecordFile | None = None,
) -> ExportHarness:
    source = FakeDecisionRecordSource(load_failure=load_failure)
    file = destination or RecordingDecisionRecordFile()
    events = RecordingEventRecorder()
    transactions = FakeTransactionRunner(ExportStores(records=source), begin_failure=begin_failure)
    return ExportHarness(
        ExportDecisions(transactions, file, events), source, file, transactions, events
    )
