/**
 * A layout primitive for a row of small items, such as badges, that continues on the next line
 * when the row is full (UI-02). The gap is 8 px, a spacing step of UI-07.
 */
import type { ReactNode } from "react";

/** Props of {@link Cluster}. */
export type ClusterProps = {
  readonly children: ReactNode;
};

/**
 * Lay out children in a row that wraps.
 *
 * @param props - The items.
 * @returns The row.
 */
export function Cluster({ children }: ClusterProps) {
  return <div className="flex min-w-0 flex-wrap items-center gap-2">{children}</div>;
}
