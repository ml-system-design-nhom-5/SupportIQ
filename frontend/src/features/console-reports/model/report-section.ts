/**
 * A section of the report (console UI design, Reports): a panel title and its figures, each a
 * label in business language, a value with its unit, and its target (UI-44).
 */
import { NO_TARGET_TEXT } from "@/features/console-reports/model/report-targets";

/** What a section whose figures are always there would say without them. */
export const NO_FIGURES_TEXT = "No figures for this period.";

/** A section of the report. */
export type ReportSectionId =
  | "tickets"
  | "draft_decisions"
  | "speed"
  | "ai_health_and_cost"
  | "escalations"
  | "ai_outcomes"
  | "edits_and_rejections"
  | "ai_reasons";

/** One figure of the report, formatted for display. */
export type ReportFigure = {
  /** Unique within its section: the field, or the raw code of the contract (TS-24). */
  readonly id: string;
  readonly label: string;
  /** The value with its unit, or "No data" when `backend` left it out. */
  readonly value: string;
  /** The target from the requirements, or "No target". */
  readonly target: string;
};

/** One panel of the report. */
export type ReportSection = {
  readonly id: ReportSectionId;
  readonly title: string;
  readonly figures: readonly ReportFigure[];
  /** What the panel says when it has no figures. */
  readonly emptyText: string;
};

/** A figure without a target: its ID, what it is, and its value with its unit. */
export type UntargetedFigure = Omit<ReportFigure, "target">;

/**
 * Build a figure for which the requirements give no target.
 *
 * @param figure - The ID, the label, and the value.
 * @returns The figure with "No target".
 */
export function buildFigure(figure: UntargetedFigure): ReportFigure {
  return { ...figure, target: NO_TARGET_TEXT };
}
