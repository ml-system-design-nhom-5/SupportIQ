/**
 * A panel of figures with their units and targets (console UI design, Reports; UI-44): a header
 * with the title, then a table with the columns Figure, Value, and Target. Each figure names its
 * row, so a screen reader announces it with its value and its target. A panel without figures
 * says so instead of showing an empty table.
 */
import type { LucideIcon } from "lucide-react";

import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Text } from "@/design-system/primitives/text";

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
        <table className="w-full border-collapse text-sm text-text">
          <caption className="sr-only">{title}</caption>
          <thead className="bg-background text-xs text-text-muted">
            <tr>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Figure
              </th>
              <th scope="col" className="px-4 py-2 text-right font-semibold">
                Value
              </th>
              <th scope="col" className="px-4 py-2 text-left font-semibold">
                Target
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t border-border">
                <th scope="row" className="px-4 py-2 text-left font-normal">
                  {row.label}
                </th>
                <td className="px-4 py-2 text-right font-medium whitespace-nowrap">{row.value}</td>
                <td className="px-4 py-2 text-text-muted">{row.target}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
