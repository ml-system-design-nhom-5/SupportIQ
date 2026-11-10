/**
 * A one-line text input with the `border-strong` role, which has 3:1 contrast (UI-30).
 */
import type { ComponentProps } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** Props of {@link TextInput}: the native input attributes without styling. */
export type TextInputProps = Omit<ComponentProps<"input">, "className" | "style">;

/**
 * Render a text input.
 *
 * @param props - The native input attributes.
 * @returns The input.
 */
export function TextInput(props: TextInputProps) {
  return (
    <input
      className={cn(
        "h-8 w-full rounded-md border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted aria-invalid:border-danger sm:text-sm",
        FOCUS_RING_CLASSES,
      )}
      {...props}
    />
  );
}
