/**
 * The header row of a {@link Panel}: an icon, a heading, and optional trailing content.
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Icon } from "@/design-system/primitives/icon";

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
  return (
    <div className="flex items-center gap-2 border-b border-border px-4 py-4 sm:px-6">
      <Icon icon={icon} />
      <Heading className="text-base font-semibold">{title}</Heading>
      {trailing === undefined ? null : <div className="ml-auto">{trailing}</div>}
    </div>
  );
}
