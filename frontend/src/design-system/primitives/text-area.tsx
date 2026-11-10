/**
 * A multi-line text input with the `border-strong` role (UI-30). Four rows give the 120 px box
 * of the shop design.
 */
import type { ComponentProps } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** The number of visible rows of the shop message box. */
const DEFAULT_ROW_COUNT = 4;

/** Props of {@link TextArea}: the native textarea attributes without styling. */
export type TextAreaProps = Omit<ComponentProps<"textarea">, "className" | "style">;

/**
 * Render a text area.
 *
 * @param props - The native textarea attributes.
 * @returns The text area.
 */
export function TextArea({ rows = DEFAULT_ROW_COUNT, ...props }: TextAreaProps) {
  return (
    <textarea
      rows={rows}
      className={cn(
        "w-full resize-y rounded-md border border-border-strong bg-surface p-3 text-base text-text placeholder:text-text-muted aria-invalid:border-danger",
        FOCUS_RING_CLASSES,
      )}
      {...props}
    />
  );
}
