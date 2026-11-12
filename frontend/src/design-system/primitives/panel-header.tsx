/**
 * The header row of a {@link Panel}: an icon, a heading, and optional trailing content.
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

const headingVariants = cva("font-semibold", {
  variants: { density: { comfortable: "text-base", compact: "text-sm" } },
});

/** Props of {@link PanelHeader}. */
export type PanelHeaderProps = {
  readonly icon: LucideIcon;
  /** The heading level in the page outline. */
  readonly level: 2 | 3;
  readonly title: string;
  readonly trailing?: ReactNode;
};

/**
 * Render the header row of a panel.
 *
 * @param props - The icon, the heading level and text, and the trailing content.
 * @returns The header.
 */
export function PanelHeader({ icon, level, title, trailing }: PanelHeaderProps) {
  const Heading = level === 2 ? "h2" : "h3";
  const density = use(PanelDensityContext);
  return (
    <div className={headerVariants({ density })}>
      <Icon icon={icon} />
      <Heading className={headingVariants({ density })}>{title}</Heading>
      {trailing === undefined ? null : <div className="ml-auto">{trailing}</div>}
    </div>
  );
}
