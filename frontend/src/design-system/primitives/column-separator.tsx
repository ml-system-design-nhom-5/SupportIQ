/**
 * The splitter between two console columns (console UI design, Column controls): the window
 * splitter of WAI-ARIA, which `react-resizable-panels` renders with the role `separator`,
 * `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, and `aria-controls`. It takes the focus, and
 * the left and right arrow keys move it (UI-30).
 */
import { GripVertical } from "lucide-react";
import type { KeyboardEvent } from "react";
import { Separator } from "react-resizable-panels";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link ColumnSeparator}. */
export type ColumnSeparatorProps = {
  /** The name, such as "Resize inbox". */
  readonly label: string;
  /** Handles a key that the library leaves alone, such as Enter for the column after it. */
  readonly onKeyDown?: (event: KeyboardEvent<HTMLDivElement>) => void;
};

/**
 * Render the splitter.
 *
 * @param props - The name and the key handler.
 * @returns The splitter.
 */
export function ColumnSeparator({ label, onKeyDown }: ColumnSeparatorProps) {
  return (
    <Separator
      aria-label={label}
      className={cn("flex w-4 shrink-0 items-center justify-center", FOCUS_RING_CLASSES)}
      {...(onKeyDown === undefined ? {} : { onKeyDown })}
    >
      <span className="flex rounded-sm border border-border bg-surface py-1 text-text-muted">
        <Icon icon={GripVertical} size="sm" />
      </span>
    </Separator>
  );
}
