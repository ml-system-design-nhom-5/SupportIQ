/**
 * A labelled input with an optional hint and error (UI-30: every input has a label). The error is
 * announced and linked to the input by the caller through `aria-describedby`.
 */
import type { ReactNode } from "react";

import { FieldLabel } from "@/design-system/primitives/field-label";

/** Props of {@link FormField}. */
export type FormFieldProps = {
  /** The `id` of the input inside. */
  readonly inputId: string;
  readonly label: string;
  /** The input element. */
  readonly children: ReactNode;
};

/**
 * Render a label and its input.
 *
 * @param props - The input's `id`, the label, and the input.
 * @returns The field.
 */
export function FormField({ inputId, label, children }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      {children}
    </div>
  );
}
