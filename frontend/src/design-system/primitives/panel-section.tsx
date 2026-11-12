/**
 * One padded section of a {@link Panel}. Sections after the first get a divider.
 */
import { cva } from "class-variance-authority";
import { type ReactNode, use } from "react";

import { PanelDensityContext } from "@/design-system/primitives/panel-density";

const panelSectionVariants = cva("border-border not-first:border-t", {
  variants: {
    layout: {
      content: "flex flex-col",
      centered: "flex flex-col items-center gap-2 text-center",
    },
    density: { comfortable: "px-4 sm:px-6", compact: "px-4" },
  },
  compoundVariants: [
    { layout: "content", density: "comfortable", className: "gap-4 py-4" },
    { layout: "content", density: "compact", className: "gap-3 py-3" },
    { layout: "centered", density: "comfortable", className: "py-8" },
    { layout: "centered", density: "compact", className: "py-6" },
  ],
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
  const density = use(PanelDensityContext);
  return <div className={panelSectionVariants({ layout, density })}>{children}</div>;
}
