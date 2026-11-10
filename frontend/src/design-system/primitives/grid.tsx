/**
 * A grid of equal columns: two at phone width and three from the `sm` breakpoint, as the product
 * catalog of the shop design shows.
 */
import type { ReactNode } from "react";

/** Props of {@link Grid}. */
export type GridProps = {
  /** `ul` keeps list semantics for a list of cards. */
  readonly as?: "div" | "ul";
  readonly label?: string;
  readonly children: ReactNode;
};

/**
 * Render a responsive grid.
 *
 * @param props - The element, its label, and the cells.
 * @returns The grid.
 */
export function Grid({ as: Element = "div", label, children }: GridProps) {
  return (
    <Element aria-label={label} className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
      {children}
    </Element>
  );
}
