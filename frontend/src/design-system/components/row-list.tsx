/**
 * A list of rows in a panel, such as My orders and Support. Each row is a {@link RowListItem}.
 */
import type { ReactNode } from "react";

/** Props of {@link RowList}. */
export type RowListProps = {
  /** The accessible name of the list. */
  readonly label: string;
  readonly children: ReactNode;
};

/**
 * Render the list.
 *
 * @param props - The label and the rows.
 * @returns The list inside a panel.
 */
export function RowList({ label, children }: RowListProps) {
  return (
    <ul
      aria-label={label}
      className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-sm"
    >
      {children}
    </ul>
  );
}
