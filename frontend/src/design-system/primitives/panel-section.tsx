/**
 * One padded section of a {@link Panel}. Sections after the first get a divider.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const panelSectionVariants = cva("border-border px-4 py-4 not-first:border-t sm:px-6", {
  variants: {
    layout: {
      content: "flex flex-col gap-4",
      centered: "flex flex-col items-center gap-2 py-8 text-center",
    },
  },
});

/** `content` pads like the card body of the designs; `centered` centers a state message. */
export type PanelSectionLayout = "content" | "centered";

/** Props of {@link PanelSection}. */
export type PanelSectionProps = {
  readonly layout?: PanelSectionLayout;
  readonly children: ReactNode;
};

/**
 * Render a section of a panel.
 *
 * @param props - The layout and the content.
 * @returns The section.
 */
export function PanelSection({ layout = "content", children }: PanelSectionProps) {
  return <div className={panelSectionVariants({ layout })}>{children}</div>;
}
