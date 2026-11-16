/**
 * The 48 px rail of a collapsed console column (console UI design, Column controls): the button
 * that opens the column, a mark of something that the column hides, and the icon of the column,
 * which is decorative. A mark has a name, so it never relies on color alone (UI-11). The layout
 * names the column with the landmark around the rail, which stays the same open or collapsed.
 */
import type { LucideIcon } from "lucide-react";

import { Icon } from "@/design-system/primitives/icon";
import { IconButton } from "@/design-system/primitives/icon-button";

/** A mark on the rail, such as the staff note of a collapsed AI sidebar. */
export type ColumnRailMark = {
  readonly label: string;
  readonly icon: LucideIcon;
};

/** Props of {@link ColumnRail}. */
export type ColumnRailProps = {
  /** The name of the open button, such as "Open inbox". */
  readonly openLabel: string;
  readonly openIcon: LucideIcon;
  /** The icon of the column. */
  readonly icon: LucideIcon;
  /** Absent, or undefined, for a rail without a mark. */
  readonly mark?: ColumnRailMark | undefined;
  readonly onOpen: () => void;
};

/**
 * Render the rail.
 *
 * @param props - The name of the open button, the icons, the mark, and the open handler.
 * @returns The rail.
 */
export function ColumnRail({ openLabel, openIcon, icon, mark, onOpen }: ColumnRailProps) {
  return (
    <div className="flex h-full flex-col items-center gap-3 py-3">
      <IconButton label={openLabel} icon={openIcon} isExpanded={false} onClick={onOpen} />
      {mark === undefined ? null : (
        <span
          role="img"
          aria-label={mark.label}
          title={mark.label}
          className="flex rounded-full border border-ai/35 bg-ai-subtle p-1 text-ai"
        >
          <Icon icon={mark.icon} size="sm" />
        </span>
      )}
      <Icon icon={icon} tone="muted" />
    </div>
  );
}
