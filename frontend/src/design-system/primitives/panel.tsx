/**
 * A panel on the page background: the card of the shop and admin designs, with the `surface`
 * role, a border, the large radius, and the first elevation level (UI-09). A console panel is
 * `compact`, and one that holds AI output has the `ai` tone, a border tinted with the `ai` role
 * (console UI design, mockups).
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { type PanelDensity, PanelDensityContext } from "@/design-system/primitives/panel-density";

const panelVariants = cva("flex flex-col overflow-hidden rounded-lg border bg-surface shadow-sm", {
  variants: { tone: { default: "border-border", ai: "border-ai/35" } },
});

/** `ai` marks a panel of AI output; `default` is every other panel. */
export type PanelTone = "default" | "ai";

/** Props of {@link Panel}. */
export type PanelProps = {
  /** `section` with a label makes the panel a landmark; `div` is the default. */
  readonly as?: "div" | "section" | "article";
  /** The accessible name of a `section` panel without a visible heading. */
  readonly label?: string;
  readonly tone?: PanelTone;
  /** `compact` in the console; the header and the sections of the panel follow it. */
  readonly density?: PanelDensity;
  readonly children: ReactNode;
};

/**
 * Render a panel. Its content is laid out by {@link PanelSection} and {@link PanelHeader}.
 *
 * @param props - The element, its label, the tone, the density, and the content.
 * @returns The panel.
 */
export function Panel({
  as: Element = "div",
  label,
  tone = "default",
  density = "comfortable",
  children,
}: PanelProps) {
  return (
    <Element aria-label={label} className={panelVariants({ tone })}>
      <PanelDensityContext value={density}>{children}</PanelDensityContext>
    </Element>
  );
}
