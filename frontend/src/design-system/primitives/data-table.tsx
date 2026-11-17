/**
 * A table of rows with named columns, named by a visually hidden caption. The `comfortable` table
 * is the table of the admin area (admin UI design, Accounts; desktop widths, UI-33): a panel of
 * its own, rows with 12 px of padding, and row headers in semibold that a screen can move the
 * focus to (UI-30). The `compact` table sits inside a console panel, below its header, such as
 * the figures of a report (console UI design, reports.png): no panel of its own, rows with 8 px
 * of padding, and row headers in the regular weight. Its rows have no actions, so its row headers
 * are not focus targets and need no ID that is unique in the page.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

const cellVariants = cva("px-4 align-middle", {
  variants: {
    kind: { columnHeader: "py-2 text-xs font-semibold", rowHeader: "", data: "" },
    density: { comfortable: "", compact: "" },
    align: { start: "text-left", end: "text-right" },
  },
  compoundVariants: [
    { kind: "rowHeader", density: "comfortable", className: "py-3 font-semibold wrap-anywhere" },
    { kind: "data", density: "comfortable", className: "py-3" },
    { kind: "rowHeader", density: "compact", className: "py-2 font-normal" },
    { kind: "data", density: "compact", className: "py-2" },
  ],
});

/**
 * `comfortable` is the table of the admin area, in a panel of its own; `compact` sits inside a
 * console panel, below its header.
 */
export type DataTableDensity = "comfortable" | "compact";

/** One column of a {@link DataTable}. */
export type DataTableColumn<Key extends string> = {
  readonly key: Key;
  readonly label: string;
  readonly align?: "start" | "end";
  /** Marks the column whose cell names its row, so a screen reader announces it with each cell. */
  readonly isRowHeader?: boolean;
};

/** One row of a {@link DataTable}: a stable ID (TS-24) and a cell for each column. */
export type DataTableRow<Key extends string> = {
  readonly id: string;
  readonly cells: Readonly<Record<Key, ReactNode>>;
};

/** Props of {@link DataTable}. */
export type DataTableProps<Key extends string> = {
  /** The accessible name of the table. */
  readonly caption: string;
  readonly columns: readonly DataTableColumn<Key>[];
  readonly rows: readonly DataTableRow<Key>[];
  /** `comfortable` by default. */
  readonly density?: DataTableDensity;
};

/** Props of the cell of one row in one column. */
type BodyCellProps<Key extends string> = {
  readonly row: DataTableRow<Key>;
  readonly column: DataTableColumn<Key>;
  readonly density: DataTableDensity;
};

/**
 * Build the element ID of the row header of a row. The header stays while the actions of its row
 * change, so a screen can move the focus to it (UI-30).
 *
 * @param rowId - The stable ID of the row.
 * @returns The element ID.
 */
export function buildRowHeaderId(rowId: string): string {
  return `row-header-${rowId}`;
}

/**
 * Render a table.
 *
 * @param props - The caption, the columns, the rows, and the density.
 * @returns The table, inside a panel of its own when it is `comfortable`.
 */
export function DataTable<Key extends string>({
  caption,
  columns,
  rows,
  density = "comfortable",
}: DataTableProps<Key>) {
  const table = (
    <table className="w-full border-collapse text-sm text-text">
      <caption className="sr-only">{caption}</caption>
      <thead className="bg-background text-text-muted">
        <tr>
          {columns.map((column) => (
            <th
              key={column.key}
              scope="col"
              className={cellVariants({
                kind: "columnHeader",
                density,
                align: column.align ?? "start",
              })}
            >
              {column.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-t border-border">
            {columns.map((column) => (
              <BodyCell key={column.key} row={row} column={column} density={density} />
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
  if (density === "compact") {
    return table;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
      {table}
    </div>
  );
}

/**
 * Render the cell of a row in a column: a row header when the column names its rows, a data cell
 * otherwise. Only a `comfortable` row header is a focus target.
 *
 * @param props - The row, the column, and the density.
 * @returns The cell.
 */
function BodyCell<Key extends string>({ row, column, density }: BodyCellProps<Key>) {
  const align = column.align ?? "start";
  const content = row.cells[column.key];
  if (column.isRowHeader !== true) {
    return <td className={cellVariants({ kind: "data", density, align })}>{content}</td>;
  }
  const rowHeaderClasses = cellVariants({ kind: "rowHeader", density, align });
  if (density === "compact") {
    return (
      <th scope="row" className={rowHeaderClasses}>
        {content}
      </th>
    );
  }
  return (
    <th
      id={buildRowHeaderId(row.id)}
      scope="row"
      tabIndex={-1}
      className={cn(rowHeaderClasses, FOCUS_RING_CLASSES, "focus-visible:-outline-offset-2")}
    >
      {content}
    </th>
  );
}
