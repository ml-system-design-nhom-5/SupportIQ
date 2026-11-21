/**
 * A panel on the page background: the card of the shop and admin designs, with the `surface`
 * role, a border, the large radius, and the first elevation level (UI-09). A console panel is
 * `compact`, and one that holds AI output has the `ai` tone, a border tinted with the `ai` role
 * (console UI design, mockups). The reply area has the `fill` height: it takes the free height of
 * its column, at least the reply panel height, so its action bar sits at the bottom of the column
 * (placement rule 2), and it grows with its content, never shrinks below it, while the column
 * scrolls. It clips its content to its rounded border without becoming a scroll container, so a
 * sticky child, such as an action bar, sticks to the scrolling column.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

import { type PanelDensity, PanelDensityContext } from "@/design-system/primitives/panel-density";

const panelVariants = cva("flex flex-col overflow-clip rounded-lg border bg-surface shadow-sm", {
  variants: {
    tone: { default: "border-border", ai: "border-ai/35" },
    height: { content: "", fill: "min-h-reply-panel shrink-0 grow" },
  },
});

/** `ai` marks a panel of AI output; `default` is every other panel. */
export type PanelTone = "default" | "ai";

/**
 * `fill` takes the free height of a flex column, at least the reply panel height, for the reply
 * area; `content` fits the content, for every other panel.
 */
export type PanelHeight = "content" | "fill";

/** Props of {@link Panel}. */
export type PanelProps = {
  /** `section` with a label makes the panel a landmark; `div` is the default. */
  readonly as?: "div" | "section" | "article";
  /** The accessible name of a `section` panel without a visible heading. */
  readonly label?: string;
  readonly tone?: PanelTone;
  /** `fill` for the reply area in the middle column of the console. */
  readonly height?: PanelHeight;
  /** `compact` in the console; the header and the sections of the panel follow it. */
  readonly density?: PanelDensity;
  readonly children: ReactNode;
};

/**
 * Render a panel. Its content is laid out by {@link PanelSection} and {@link PanelHeader}.
 *
 * @param props - The element, its label, the tone, the height, the density, and the content.
 * @returns The panel.
 */
export function Panel({
  as: Element = "div",
  label,
  tone = "default",
  height = "content",
  density = "comfortable",
  children,
}: PanelProps) {
  return (
    <Element aria-label={label} className={panelVariants({ tone, height })}>
      <PanelDensityContext value={density}>{children}</PanelDensityContext>
    </Element>
  );
}
