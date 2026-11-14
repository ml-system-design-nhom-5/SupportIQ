/**
 * The sections of the report that break a count down by code (console UI design, Reports;
 * FR-10): edits and rejections by staff reason, escalations by staff reason, completed drafts by
 * status, and drafts by AI reason. Each item from `backend` is one figure, keyed by its raw code,
 * because two codes that this version does not know both show as an unknown reason (CON-22,
 * TS-24). Labels come from the one presentation of each code (UI-12, CODE-48).
 */
import {
  type CompletedDraftStatusName,
  presentationByAiReasonCode,
  presentationByCompletedDraftStatus,
} from "@/design-system";
import type {
  ConsoleReportContract,
  StaffReasonReplyCountContract,
} from "@/features/console-reports/api/contract-types";
import {
  buildFigure,
  NO_FIGURES_TEXT,
  type ReportFigure,
  type ReportSection,
} from "@/features/console-reports/model/report-section";
import { formatCountOf } from "@/features/console-reports/model/report-units";
import {
  type ShownStaffReasonCode,
  shownStaffReasonCodeLabels,
  toAiReasonCode,
  toStaffReasonCodes,
} from "@/features/console-tickets";

/** The statuses of `CompletedDraftStatus` that this version knows. */
const completedDraftStatuses: ReadonlySet<string> = new Set([
  "draft_ready",
  "abstained",
  "escalation_recommended",
  "llm_unavailable",
  "unavailable",
]);

type Escalations = ConsoleReportContract["escalations"];
type DraftStatusCount = ConsoleReportContract["ai_outcomes"]["by_draft_status"][number];
type AiReasonCount = ConsoleReportContract["ai_outcomes"]["by_reason_code"][number];

/**
 * Build the edits and the rejections of ready drafts by staff reason code (ADR-0006).
 *
 * @param decisions - The `draft_decisions` of the report.
 * @returns The section: the edits by reason, then the rejections by reason.
 */
export function buildStaffReasonsSection(
  decisions: ConsoleReportContract["draft_decisions"],
): ReportSection {
  return {
    id: "edits_and_rejections",
    title: "Edits and rejections by staff reason",
    figures: [
      ...decisions.edit_by_reason.map((item) => buildStaffReasonFigure(item, "Edited")),
      ...decisions.reject_by_reason.map((item) => buildStaffReasonFigure(item, "Rejected")),
    ],
    emptyText: "No edits or rejections with a reason in this period.",
  };
}

/**
 * Build the escalations of the period, then the escalations of each staff reason code.
 *
 * @param escalations - The `escalations` of the report.
 * @returns The section.
 */
export function buildEscalationsSection(escalations: Escalations): ReportSection {
  return {
    id: "escalations",
    title: "Escalations by staff reason",
    figures: [
      buildFigure({
        id: "escalations",
        label: "Escalations",
        value: formatCountOf(escalations.escalation_count, "escalation"),
      }),
      ...escalations.by_reason.map((item) =>
        buildFigure({
          id: `escalation-${item.staff_reason_code}`,
          label: shownStaffReasonCodeLabels[toShownStaffReasonCode(item.staff_reason_code)],
          value: formatCountOf(item.escalation_count, "escalation"),
        }),
      ),
    ],
    emptyText: NO_FIGURES_TEXT,
  };
}

/**
 * Build the completed draft parts by status.
 *
 * @param statusCounts - The `by_draft_status` of the report.
 * @returns The section.
 */
export function buildAiOutcomesSection(statusCounts: readonly DraftStatusCount[]): ReportSection {
  return {
    id: "ai_outcomes",
    title: "AI outcomes",
    figures: statusCounts.map((item) =>
      buildFigure({
        id: `status-${item.draft_status}`,
        label: presentationByCompletedDraftStatus[toCompletedDraftStatus(item.draft_status)].label,
        value: formatCountOf(item.suggestion_count, "suggestion"),
      }),
    ),
    emptyText: "No suggestions were completed in this period.",
  };
}

/**
 * Build the completed draft parts by AI reason code.
 *
 * @param reasonCounts - The `by_reason_code` of the report.
 * @returns The section.
 */
export function buildAiReasonsSection(reasonCounts: readonly AiReasonCount[]): ReportSection {
  return {
    id: "ai_reasons",
    title: "AI reasons",
    figures: reasonCounts.map((item) =>
      buildFigure({
        id: `reason-${item.reason_code}`,
        label: presentationByAiReasonCode[toAiReasonCode(item.reason_code)].label,
        value: formatCountOf(item.suggestion_count, "suggestion"),
      }),
    ),
    emptyText: "No suggestion carried an AI reason in this period.",
  };
}

/**
 * Map a completed draft status from `backend`.
 *
 * @param value - A `CompletedDraftStatus`.
 * @returns The status, or `unknown` for a status that this version does not know (CON-22).
 */
export function toCompletedDraftStatus(value: string): CompletedDraftStatusName {
  return isCompletedDraftStatus(value) ? value : "unknown";
}

/**
 * Build the figure of the replies of one decision with one staff reason code.
 *
 * @param item - The code and its replies.
 * @param decision - "Edited" or "Rejected".
 * @returns The figure, such as "Edited: Tone or clarity", keyed by the decision and the raw code.
 */
function buildStaffReasonFigure(
  item: StaffReasonReplyCountContract,
  decision: "Edited" | "Rejected",
): ReportFigure {
  const label = shownStaffReasonCodeLabels[toShownStaffReasonCode(item.staff_reason_code)];
  return buildFigure({
    id: `${decision.toLowerCase()}-${item.staff_reason_code}`,
    label: `${decision}: ${label}`,
    value: formatCountOf(item.reply_count, "reply"),
  });
}

/**
 * Map one staff reason code from `backend`.
 *
 * @param value - A `StaffReasonCode`.
 * @returns The code, or `unknown` for a code that this version does not know (CON-22).
 */
function toShownStaffReasonCode(value: string): ShownStaffReasonCode {
  const [code = "unknown"] = toStaffReasonCodes([value]);
  return code;
}

/**
 * Tell whether a value is a completed draft status that this version knows.
 *
 * @param value - A `CompletedDraftStatus`.
 * @returns True for a value of the contract's `CompletedDraftStatus`.
 */
function isCompletedDraftStatus(
  value: string,
): value is Exclude<CompletedDraftStatusName, "unknown"> {
  return completedDraftStatuses.has(value);
}
