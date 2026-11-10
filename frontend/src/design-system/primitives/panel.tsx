/**
 * A panel on the page background: the card of the shop and admin designs, with the `surface`
 * role, a border, the large radius, and the first elevation level (UI-09).
 */
import type { ReactNode } from "react";

/** Props of {@link Panel}. */
export type PanelProps = {
  /** `section` with a label makes the panel a landmark; `div` is the default. */
  readonly as?: "div" | "section" | "article";
  /** The accessible name of a `section` panel without a visible heading. */
  readonly label?: string;
  readonly children: ReactNode;
};

/**
 * Render a panel. Its content is laid out by {@link PanelSection} and {@link PanelHeader}.
 *
 * @param props - The element, its label, and the content.
 * @returns The panel.
 */
export function Panel({ as: Element = "div", label, children }: PanelProps) {
  return (
    <Element
      aria-label={label}
      className="flex flex-col overflow-hidden rounded-lg border border-border bg-surface shadow-sm"
    >
      {children}
    </Element>
  );
}
