/**
 * The figures of a report (console UI design, reports.png): one panel per section in a grid of
 * three columns at the console width, each figure with its value and its target (UI-44).
 */
import {
  Activity,
  CircleArrowUp,
  FileCheck,
  Inbox,
  ListChecks,
  type LucideIcon,
  PencilLine,
  Sparkles,
  Timer,
} from "lucide-react";

import { FigureTable, Grid } from "@/design-system";
import type {
  ReportSection,
  ReportSectionId,
} from "@/features/console-reports/model/report-section";

/** The icon in the header of each section. */
const iconBySectionId: Readonly<Record<ReportSectionId, LucideIcon>> = {
  tickets: Inbox,
  draft_decisions: FileCheck,
  speed: Timer,
  ai_health_and_cost: Activity,
  escalations: CircleArrowUp,
  ai_outcomes: Sparkles,
  edits_and_rejections: PencilLine,
  ai_reasons: ListChecks,
};

/** Props of {@link ReportGrid}. */
type ReportGridProps = {
  readonly sections: readonly ReportSection[];
};

/**
 * Render the sections of a report.
 *
 * @param props - The sections, in the order of the page.
 * @returns The grid of panels.
 */
export function ReportGrid({ sections }: ReportGridProps) {
  return (
    <Grid>
      {sections.map((section) => (
        <FigureTable
          key={section.id}
          icon={iconBySectionId[section.id]}
          title={section.title}
          rows={section.figures}
          emptyText={section.emptyText}
        />
      ))}
    </Grid>
  );
}
