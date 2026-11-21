/**
 * The visible label of an input (UI-30), on Radix Label (UI-31).
 */
import * as LabelPrimitive from "@radix-ui/react-label";
import type { ReactNode } from "react";

/** Props of {@link FieldLabel}. */
export type FieldLabelProps = {
  /** The `id` of the labelled input. */
  readonly htmlFor: string;
  readonly children: ReactNode;
};

/**
 * Render the label of an input.
 *
 * @param props - The input's `id` and the label text.
 * @returns The label.
 */
export function FieldLabel({ htmlFor, children }: FieldLabelProps) {
  return (
    <LabelPrimitive.Root htmlFor={htmlFor} className="text-sm font-medium text-text">
      {children}
    </LabelPrimitive.Root>
  );
}
