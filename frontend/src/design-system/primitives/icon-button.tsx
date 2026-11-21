/**
 * A small button that shows only an icon, such as Collapse inbox (console UI design, Column
 * controls). Its name comes from `label`, so assistive technology reads it; the icon is decorative.
 */
import type { LucideIcon } from "lucide-react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link IconButton}. */
export type IconButtonProps = {
  readonly label: string;
  readonly icon: LucideIcon;
  /** Whether the column that the button controls is open; absent for other buttons. */
  readonly isExpanded?: boolean;
  readonly onClick: () => void;
};

/**
 * Render the button.
 *
 * @param props - The name, the icon, whether it is expanded, and the click handler.
 * @returns The button.
 */
export function IconButton({ label, icon, isExpanded, onClick }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-expanded={isExpanded}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-sm text-text-muted hover:bg-background hover:text-text",
        FOCUS_RING_CLASSES,
      )}
      onClick={onClick}
    >
      <Icon icon={icon} size="sm" />
    </button>
  );
}
