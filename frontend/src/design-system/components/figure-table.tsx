/**
 * A panel of figures with their units and targets (console UI design, Reports; UI-44): a header
 * with the title, then a compact {@link DataTable} with the columns Figure, Value, and Target.
 * Each figure names its row, so a screen reader announces it with its value and its target. The
 * value keeps its unit on one line, and the target is muted, as in reports.png. A panel without
 * figures says so instead of showing an empty table.
 */
import type { LucideIcon } from "lucide-react";

import {
  DataTable,
  type DataTableColumn,
  type DataTableRow,
} from "@/design-system/primitives/data-table";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Text } from "@/design-system/primitives/text";

const figureColumns: readonly DataTableColumn<FigureColumn>[] = [
  { key: "figure", label: "Figure", isRowHeader: true },
  { key: "value", label: "Value", align: "end" },
  { key: "target", label: "Target" },
];

/** The columns of the table. */
type FigureColumn = "figure" | "value" | "target";

/** One figure of a {@link FigureTable}, already formatted for display. */
export type FigureTableRow = {
  /** Stable within the table; it is also the key of the row (TS-24). */
  readonly id: string;
  /** What the figure is, in business language, such as "Created, assisted". */
  readonly label: string;
  /** The value with its unit, such as "120 tickets". */
  readonly value: string;
  /** The target with its unit, such as "At most 4 s", or "No target". */
  readonly target: string;
};

/** Props of {@link FigureTable}. */
export type FigureTableProps = {
  readonly icon: LucideIcon;
  /** The heading of the panel and the name of its table, such as "Tickets". */
  readonly title: string;
  readonly rows: readonly FigureTableRow[];
  /** What the panel says instead of the table when there are no rows. */
  readonly emptyText: string;
};

/**
 * Render a panel of figures.
 *
 * @param props - The icon, the title, the figures, and the text without figures.
 * @returns The panel with its table, or with the text without figures.
 */
export function FigureTable({ icon, title, rows, emptyText }: FigureTableProps) {
  return (
    <Panel density="compact">
      <PanelHeader icon={icon} level={2} title={title} />
      {rows.length === 0 ? (
        <PanelSection>
          <Text tone="muted">{emptyText}</Text>
        </PanelSection>
      ) : (
        <DataTable
          density="compact"
          caption={title}
          columns={figureColumns}
          rows={rows.map((row) => buildFigureRow(row))}
        />
      )}
    </Panel>
  );
}

/**
 * Build the table row of a figure.
 *
 * @param row - The figure.
 * @returns The row: the label, the value on one line, and the muted target.
 */
function buildFigureRow(row: FigureTableRow): DataTableRow<FigureColumn> {
  return {
    id: row.id,
    cells: {
      figure: row.label,
      value: <span className="font-medium whitespace-nowrap">{row.value}</span>,
      target: <Text tone="muted">{row.target}</Text>,
    },
  };
}
