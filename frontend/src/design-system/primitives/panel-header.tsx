/**
 * The header row of a {@link Panel}: an optional icon, a heading, and optional trailing content. A
 * heading with a focus target ID can take the focus from a script and, like the ticket heading,
 * shows no outline then. The header draws the line under it, whatever follows; it carries
 * `data-panel-header` so that a {@link PanelSection} right after it draws no second line.
 */
import { cva } from "class-variance-authority";
import type { LucideIcon } from "lucide-react";
import { type ReactNode, use } from "react";

import { Icon } from "@/design-system/primitives/icon";
import { PanelDensityContext } from "@/design-system/primitives/panel-density";

const headerVariants = cva("flex items-center gap-2 border-b border-border", {
  variants: {
    density: { comfortable: "px-4 py-4 sm:px-6", compact: "px-4 py-3" },
  },
});

const headingVariants = cva("font-semibold outline-none", {
  variants: { density: { comfortable: "text-base", compact: "text-sm" } },
});

/** Props of {@link PanelHeader}. */
export type PanelHeaderProps = {
  /** Absent for a panel whose design shows no icon, such as the panels of the Versions screen. */
  readonly icon?: LucideIcon;
  /** The heading level in the page outline. */
  readonly level: 2 | 3;
  readonly title: string;
  readonly trailing?: ReactNode;
  /**
   * The ID of the heading, which a script moves the focus to, such as when the element that held
   * the focus is gone. The heading can then hold the focus, but Tab never reaches it (UI-30).
   */
  readonly focusTargetId?: string;
};

/**
 * Render the header row of a panel.
 *
 * @param props - The icon, the heading level and text, the trailing content, and the focus target
 *   ID.
 * @returns The header.
 */
export function PanelHeader({ icon, level, title, trailing, focusTargetId }: PanelHeaderProps) {
  const Heading = level === 2 ? "h2" : "h3";
  const density = use(PanelDensityContext);
  return (
    <div data-panel-header className={headerVariants({ density })}>
      {icon === undefined ? null : <Icon icon={icon} />}
      <Heading
        id={focusTargetId}
        tabIndex={focusTargetId === undefined ? undefined : -1}
        className={headingVariants({ density })}
      >
        {title}
      </Heading>
      {trailing === undefined ? null : <div className="ml-auto">{trailing}</div>}
    </div>
  );
}
