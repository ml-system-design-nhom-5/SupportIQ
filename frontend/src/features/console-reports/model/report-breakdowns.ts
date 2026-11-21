/**
 * The sections of the report that break a count down by code (console UI design, Reports;
 * FR-10): edits and rejections by staff reason, escalations by staff reason, completed drafts by
 * status, and drafts by AI reason. Each count from `backend` is one figure, keyed by its raw code,
 * because two codes that this version does not know both show as an unknown reason (CON-22,
 * TS-24). Labels come from the one presentation of each code (UI-12, CODE-48). A count without a
 * member that the contract requires stops the mapping (CODE-32).
 */
import {
  type CompletedDraftStatusName,
  presentationByAiReasonCode,
  presentationByCompletedDraftStatus,
} from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  CompletedDraftStatusContract,
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
  shownStaffReasonCodeLabels,
  toAiReasonCode,
  toStaffReasonCode,
} from "@/features/console-tickets";

/** The statuses of `CompletedDraftStatus`, in the order of the contract. */
const completedDraftStatuses = [
  "draft_ready",
  "abstained",
  "escalation_recommended",
  "llm_unavailable",
  "unavailable",
] as const satisfies readonly CompletedDraftStatusContract[];

type Escalations = ConsoleReportContract["escalations"];
type EscalationReasonCount = Escalations["by_reason"][number];
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
  requireMembers(decisions, ["edit_by_reason", "reject_by_reason"]);
  return {
    id: "edits_and_rejections",
    title: "Edits and rejections by staff reason",
    figures: [
      ...decisions.edit_by_reason.map((reasonCount) =>
        buildStaffReasonFigure(reasonCount, "Edited"),
      ),
      ...decisions.reject_by_reason.map((reasonCount) =>
        buildStaffReasonFigure(reasonCount, "Rejected"),
      ),
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
  requireMembers(escalations, ["escalation_count", "by_reason"]);
  return {
    id: "escalations",
    title: "Escalations by staff reason",
    figures: [
      buildFigure({
        id: "escalations",
        label: "Escalations",
        value: formatCountOf(escalations.escalation_count, "escalation"),
      }),
      ...escalations.by_reason.map((reasonCount) => buildEscalationReasonFigure(reasonCount)),
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
    figures: statusCounts.map((statusCount) => buildDraftStatusFigure(statusCount)),
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
    figures: reasonCounts.map((reasonCount) => buildAiReasonFigure(reasonCount)),
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
  return completedDraftStatuses.find((status) => status === value) ?? "unknown";
}

/**
 * Build the figure of the replies of one decision with one staff reason code.
 *
 * @param reasonCount - The code and its replies.
 * @param decision - "Edited" or "Rejected".
 * @returns The figure, such as "Edited: Tone or clarity", keyed by the decision and the raw code.
 */
function buildStaffReasonFigure(
  reasonCount: StaffReasonReplyCountContract,
  decision: "Edited" | "Rejected",
): ReportFigure {
  requireMembers(reasonCount, ["staff_reason_code", "reply_count"]);
  const label = shownStaffReasonCodeLabels[toStaffReasonCode(reasonCount.staff_reason_code)];
  return buildFigure({
    id: `${decision.toLowerCase()}-${reasonCount.staff_reason_code}`,
    label: `${decision}: ${label}`,
    value: formatCountOf(reasonCount.reply_count, "reply"),
  });
}

/**
 * Build the figure of the escalations with one staff reason code.
 *
 * @param reasonCount - The code and its escalations.
 * @returns The figure, keyed by the raw code.
 */
function buildEscalationReasonFigure(reasonCount: EscalationReasonCount): ReportFigure {
  requireMembers(reasonCount, ["staff_reason_code", "escalation_count"]);
  return buildFigure({
    id: `escalation-${reasonCount.staff_reason_code}`,
    label: shownStaffReasonCodeLabels[toStaffReasonCode(reasonCount.staff_reason_code)],
    value: formatCountOf(reasonCount.escalation_count, "escalation"),
  });
}

/**
 * Build the figure of the completed draft parts with one status.
 *
 * @param statusCount - The status and its suggestions.
 * @returns The figure, keyed by the raw status.
 */
function buildDraftStatusFigure(statusCount: DraftStatusCount): ReportFigure {
  requireMembers(statusCount, ["draft_status", "suggestion_count"]);
  const status = toCompletedDraftStatus(statusCount.draft_status);
  return buildFigure({
    id: `status-${statusCount.draft_status}`,
    label: presentationByCompletedDraftStatus[status].label,
    value: formatCountOf(statusCount.suggestion_count, "suggestion"),
  });
}

/**
 * Build the figure of the completed draft parts with one AI reason code.
 *
 * @param reasonCount - The code and its suggestions.
 * @returns The figure, keyed by the raw code.
 */
function buildAiReasonFigure(reasonCount: AiReasonCount): ReportFigure {
  requireMembers(reasonCount, ["reason_code", "suggestion_count"]);
  return buildFigure({
    id: `reason-${reasonCount.reason_code}`,
    label: presentationByAiReasonCode[toAiReasonCode(reasonCount.reason_code)].label,
    value: formatCountOf(reasonCount.suggestion_count, "suggestion"),
  });
}
