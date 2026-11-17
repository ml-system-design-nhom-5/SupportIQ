/**
 * The report of a period as the Reports page shows it (console UI design, Reports; FR-10,
 * UI-44): the contract's `ConsoleReport` mapped once (TS-09) into sections of figures, each a
 * label in business language, a value with its unit, and its target. The mapping only formats
 * what `backend` sent: it never adds up, merges, or compares a figure (UI-14). A body without a
 * member that the contract requires stops the mapping, so it never shows as figures (CODE-32).
 */
import {
  formatCount,
  formatDuration,
  formatMicroUsd,
  formatShareOneDecimal,
} from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  ConsoleReportContract,
  ModeHandlingTimeContract,
} from "@/features/console-reports/api/contract-types";
import {
  buildAiOutcomesSection,
  buildAiReasonsSection,
  buildEscalationsSection,
  buildStaffReasonsSection,
} from "@/features/console-reports/model/report-breakdowns";
import { formatReportPeriod } from "@/features/console-reports/model/report-period";
import {
  buildFigure,
  NO_FIGURES_TEXT,
  type ReportFigure,
  type ReportSection,
} from "@/features/console-reports/model/report-section";
import {
  ASSISTED_HANDLING_TIME_TARGET_TEXT,
  LATENCY_P50_TARGET_TEXT,
  LATENCY_P95_TARGET_TEXT,
} from "@/features/console-reports/model/report-targets";
import { formatCountOf, formatOptional } from "@/features/console-reports/model/report-units";

/** The report of a period. */
export type ConsoleReport = {
  /** The local dates of the period that `backend` returned, such as `1 Nov 2026 – 7 Nov 2026`. */
  readonly periodText: string;
  /** Every section, in the order of the page. */
  readonly sections: readonly ReportSection[];
};

/**
 * Map the body of `getConsoleReport`.
 *
 * @param report - The report from `backend`.
 * @returns The period and the sections of figures.
 */
export function toConsoleReport(report: ConsoleReportContract): ConsoleReport {
  requireMembers(report, [
    "period",
    "ticket_counts",
    "draft_decisions",
    "escalations",
    "ai_outcomes",
    "end_to_end_latency",
    "ai_error_rate",
    "llm_cost_micro_usd",
    "handling_time",
  ]);
  requireMembers(report.period, ["start_at", "end_at"]);
  requireMembers(report.ai_outcomes, ["by_draft_status", "by_reason_code"]);
  return {
    periodText: formatReportPeriod({
      startAt: report.period.start_at,
      endAt: report.period.end_at,
    }),
    sections: [
      buildTicketsSection(report.ticket_counts),
      buildDraftDecisionsSection(report.draft_decisions),
      buildSpeedSection(report),
      buildAiHealthAndCostSection(report),
      buildEscalationsSection(report.escalations),
      buildAiOutcomesSection(report.ai_outcomes.by_draft_status),
      buildStaffReasonsSection(report.draft_decisions),
      buildAiReasonsSection(report.ai_outcomes.by_reason_code),
    ],
  };
}

/**
 * Build the tickets created and closed, by handling mode.
 *
 * @param ticketCounts - The `ticket_counts` of the report.
 * @returns The section.
 */
function buildTicketsSection(ticketCounts: ConsoleReportContract["ticket_counts"]): ReportSection {
  requireMembers(ticketCounts, ["created", "closed"]);
  const { created, closed } = ticketCounts;
  for (const modeCounts of [created, closed]) {
    requireMembers(modeCounts, ["assisted_count", "manual_count"]);
  }
  return {
    id: "tickets",
    title: "Tickets",
    figures: [
      buildFigure({
        id: "created-assisted",
        label: "Created, assisted",
        value: formatCountOf(created.assisted_count, "ticket"),
      }),
      buildFigure({
        id: "created-manual",
        label: "Created, manual",
        value: formatCountOf(created.manual_count, "ticket"),
      }),
      buildFigure({
        id: "closed-assisted",
        label: "Closed, assisted",
        value: formatCountOf(closed.assisted_count, "ticket"),
      }),
      buildFigure({
        id: "closed-manual",
        label: "Closed, manual",
        value: formatCountOf(closed.manual_count, "ticket"),
      }),
    ],
    emptyText: NO_FIGURES_TEXT,
  };
}

/**
 * Build the staff decisions about ready drafts, each with its share when `backend` sent one.
 *
 * @param decisions - The `draft_decisions` of the report.
 * @returns The section.
 */
function buildDraftDecisionsSection(
  decisions: ConsoleReportContract["draft_decisions"],
): ReportSection {
  requireMembers(decisions, ["approve_count", "edit_count", "reject_count"]);
  return {
    id: "draft_decisions",
    title: "Draft decisions",
    figures: [
      buildFigure({
        id: "approved",
        label: "Approved",
        value: formatDecision(decisions.approve_count, decisions.approve_share),
      }),
      buildFigure({
        id: "edited",
        label: "Edited",
        value: formatDecision(decisions.edit_count, decisions.edit_share),
      }),
      buildFigure({
        id: "rejected",
        label: "Rejected",
        value: formatDecision(decisions.reject_count, decisions.reject_share),
      }),
    ],
    emptyText: NO_FIGURES_TEXT,
  };
}

/**
 * Build the end-to-end latency (NFR-08) and the handling time by mode (NFR-11), with their
 * targets.
 *
 * @param report - The report from `backend`.
 * @returns The section.
 */
function buildSpeedSection(report: ConsoleReportContract): ReportSection {
  return {
    id: "speed",
    title: "Speed",
    figures: [
      ...buildLatencyFigures(report.end_to_end_latency),
      ...buildHandlingTimeFigures(report.handling_time),
    ],
    emptyText: NO_FIGURES_TEXT,
  };
}

/**
 * Build the end-to-end latency figures (NFR-08).
 *
 * @param latency - The `end_to_end_latency` of the report.
 * @returns The p50 and the p95 with their targets, and the tickets measured.
 */
function buildLatencyFigures(
  latency: ConsoleReportContract["end_to_end_latency"],
): readonly ReportFigure[] {
  requireMembers(latency, ["ticket_count"]);
  return [
    {
      id: "latency-p50",
      label: "End-to-end latency p50",
      value: formatOptional(latency.p50_ms, formatLatency),
      target: LATENCY_P50_TARGET_TEXT,
    },
    {
      id: "latency-p95",
      label: "End-to-end latency p95",
      value: formatOptional(latency.p95_ms, formatLatency),
      target: LATENCY_P95_TARGET_TEXT,
    },
    buildFigure({
      id: "latency-tickets",
      label: "Tickets measured for latency",
      value: formatCountOf(latency.ticket_count, "ticket"),
    }),
  ];
}

/**
 * Build the handling time figures (NFR-11).
 *
 * @param handlingTime - The `handling_time` of the report.
 * @returns The median of each mode, the target of the assisted mode, and the tickets measured.
 */
function buildHandlingTimeFigures(
  handlingTime: ConsoleReportContract["handling_time"],
): readonly ReportFigure[] {
  requireMembers(handlingTime, ["assisted", "manual"]);
  const { assisted, manual } = handlingTime;
  for (const modeHandlingTime of [assisted, manual]) {
    requireMembers(modeHandlingTime, ["ticket_count"]);
  }
  return [
    {
      id: "handling-assisted",
      label: "Handling time p50, assisted",
      value: formatHandlingTime(assisted),
      target: ASSISTED_HANDLING_TIME_TARGET_TEXT,
    },
    buildFigure({
      id: "handling-manual",
      label: "Handling time p50, manual",
      value: formatHandlingTime(manual),
    }),
    buildFigure({
      id: "handling-tickets-assisted",
      label: "Closed tickets measured, assisted",
      value: formatCountOf(assisted.ticket_count, "ticket"),
    }),
    buildFigure({
      id: "handling-tickets-manual",
      label: "Closed tickets measured, manual",
      value: formatCountOf(manual.ticket_count, "ticket"),
    }),
  ];
}

/**
 * Build the AI error rate and the LLM cost (FR-10, NFR-10).
 *
 * @param report - The report from `backend`.
 * @returns The section.
 */
function buildAiHealthAndCostSection(report: ConsoleReportContract): ReportSection {
  const { ai_error_rate: errorRate, llm_cost_micro_usd: cost } = report;
  requireMembers(errorRate, ["suggestion_count", "failed_count"]);
  requireMembers(cost, ["total", "llm_call_count"]);
  return {
    id: "ai_health_and_cost",
    title: "AI health and cost",
    figures: [
      buildFigure({
        id: "ai-error-rate",
        label: "AI error rate",
        value: formatErrorRate(errorRate),
      }),
      buildFigure({
        id: "llm-cost-total",
        label: "LLM cost, total",
        value: formatMicroUsd(cost.total),
      }),
      buildFigure({
        id: "llm-cost-average",
        label: "LLM cost per suggestion that called the LLM",
        value: formatOptional(cost.average, formatMicroUsd),
      }),
      buildFigure({
        id: "llm-calls",
        label: "Suggestions that called the LLM",
        value: formatCountOf(cost.llm_call_count, "suggestion"),
      }),
    ],
    emptyText: NO_FIGURES_TEXT,
  };
}

/**
 * Format the replies of one draft decision with their share.
 *
 * @param replyCount - The replies of the decision.
 * @param share - Their share of the three decisions, absent when there was no decision.
 * @returns For example `52 replies · 46.2%`, or `0 replies · No data` without a share.
 */
function formatDecision(replyCount: number, share: number | undefined): string {
  return `${formatCountOf(replyCount, "reply")} · ${formatOptional(share, formatShareOneDecimal)}`;
}

/**
 * Format the AI error rate with the counts that `backend` computed it from.
 *
 * @param errorRate - The `ai_error_rate` of the report.
 * @returns For example `25% · 1 of 4 suggestions`, or `No data · 0 of 0 suggestions` without a
 *   share.
 */
function formatErrorRate(errorRate: ConsoleReportContract["ai_error_rate"]): string {
  const share = formatOptional(errorRate.share, formatShareOneDecimal);
  const suggestions = formatCountOf(errorRate.suggestion_count, "suggestion");
  return `${share} · ${formatCount(errorRate.failed_count)} of ${suggestions}`;
}

/**
 * Format a latency next to its target of at most some time (NFR-08). It is rounded up, so a
 * latency above the target never shows as the target itself: 12 040 ms shows as "12.1 s" next to
 * "At most 12 s".
 *
 * @param durationMs - The percentile from `backend`, in milliseconds.
 * @returns For example `3.6 s` or `12.1 s`.
 */
function formatLatency(durationMs: number): string {
  return formatDuration(durationMs, "up");
}

/**
 * Format the median handling time of one mode, rounded to the nearest: its target is relative to
 * the manual process (NFR-11), so there is no time to round against.
 *
 * @param handlingTime - The handling time of the mode.
 * @returns The duration, or "No data" when no closed ticket of the mode was measured.
 */
function formatHandlingTime(handlingTime: ModeHandlingTimeContract): string {
  return formatOptional(handlingTime.p50_ms, formatDuration);
}
