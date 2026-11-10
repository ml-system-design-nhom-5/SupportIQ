/**
 * A table of rows with named columns, for the admin area (desktop widths, UI-33).
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

const cellVariants = cva("px-4 align-middle", {
  variants: {
    kind: {
      columnHeader: "py-2 text-xs font-semibold",
      rowHeader: "py-3 font-semibold wrap-anywhere",
      data: "py-3",
    },
    align: { start: "text-left", end: "text-right" },
  },
});

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
 * @param props - The caption, the columns, and the rows.
 * @returns The table inside a panel.
 */
export function DataTable<Key extends string>({ caption, columns, rows }: DataTableProps<Key>) {
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-surface shadow-sm">
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
              {columns.map((column) =>
                column.isRowHeader === true ? (
                  <th
                    key={column.key}
                    id={buildRowHeaderId(row.id)}
                    scope="row"
                    tabIndex={-1}
                    className={cn(
                      cellVariants({ kind: "rowHeader", align: column.align ?? "start" }),
                      FOCUS_RING_CLASSES,
                      "focus-visible:-outline-offset-2",
                    )}
                  >
                    {row.cells[column.key]}
                  </th>
                ) : (
                  <td
                    key={column.key}
                    className={cellVariants({ kind: "data", align: column.align ?? "start" })}
                  >
                    {row.cells[column.key]}
                  </td>
                ),
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
