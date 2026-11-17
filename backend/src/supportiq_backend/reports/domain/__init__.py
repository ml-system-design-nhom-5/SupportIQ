"""Domain of reports: the report of a period, the decision records, and their ports."""

from supportiq_backend.reports.domain.decision_records import (
    DecisionRecord,
    ExportedDecision,
    ExportedPart,
    JsonValue,
    SuggestionSnapshot,
)
from supportiq_backend.reports.domain.errors import (
    EXPORTS_FOLDER_NAME,
    ExportPathRefusedError,
    ExportWriteFailedError,
    InvalidReportPeriodError,
)
from supportiq_backend.reports.domain.ports import (
    AiFigures,
    DecisionRecordFile,
    DecisionRecordSource,
    TicketFigures,
)
from supportiq_backend.reports.domain.report import (
    AiErrorRate,
    AiOutcomes,
    ConsoleReport,
    DraftDecisions,
    EndToEndLatency,
    Escalations,
    HandlingTime,
    LatencyPercentiles,
    LlmCost,
    ModeCounts,
    ModeHandlingTime,
    TicketCounts,
)
from supportiq_backend.reports.domain.report_rules import (
    CodeCount,
    ReportPeriod,
    build_report_period,
    compute_rounded_average,
    compute_share,
    order_code_counts,
)

__all__ = [
    "EXPORTS_FOLDER_NAME",
    "AiErrorRate",
    "AiFigures",
    "AiOutcomes",
    "CodeCount",
    "ConsoleReport",
    "DecisionRecord",
    "DecisionRecordFile",
    "DecisionRecordSource",
    "DraftDecisions",
    "EndToEndLatency",
    "Escalations",
    "ExportPathRefusedError",
    "ExportWriteFailedError",
    "ExportedDecision",
    "ExportedPart",
    "HandlingTime",
    "InvalidReportPeriodError",
    "JsonValue",
    "LatencyPercentiles",
    "LlmCost",
    "ModeCounts",
    "ModeHandlingTime",
    "ReportPeriod",
    "SuggestionSnapshot",
    "TicketCounts",
    "TicketFigures",
    "build_report_period",
    "compute_rounded_average",
    "compute_share",
    "order_code_counts",
]
