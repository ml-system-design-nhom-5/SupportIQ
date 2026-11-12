/**
 * A one-line text input with the `border-strong` role, which has 3:1 contrast (UI-30). It can show
 * fixed text before the value, such as the role prefix of a login name (account management design,
 * Create account dialog).
 */
import type { ComponentProps } from "react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** The classes of every one-line input, defined once for {@link PasswordInput} too (CODE-48). */
export const TEXT_INPUT_CLASSES = cn(
  "h-8 w-full rounded-md border border-border-strong bg-surface px-3 text-base text-text placeholder:text-text-muted aria-invalid:border-danger sm:text-sm",
  FOCUS_RING_CLASSES,
);

/** Props of {@link TextInput}: the native input attributes without styling. */
export type TextInputProps = Omit<ComponentProps<"input">, "className" | "style"> & {
  /** Fixed text before the value, in the monospace family; it is not part of the value. */
  readonly leadingText?: string;
};

/**
 * Render a text input.
 *
 * @param props - The leading text and the native input attributes.
 * @returns The input, after its leading text when there is one.
 */
export function TextInput({ leadingText, ...inputAttributes }: TextInputProps) {
  if (leadingText === undefined) {
    return <input className={TEXT_INPUT_CLASSES} {...inputAttributes} />;
  }
  return (
    <div className="flex w-full min-w-0">
      <span className="flex items-center rounded-l-md border border-r-0 border-border-strong bg-background px-2 font-mono text-xs text-text">
        {leadingText}
      </span>
      <input className={cn(TEXT_INPUT_CLASSES, "rounded-l-none")} {...inputAttributes} />
    </div>
  );
}
