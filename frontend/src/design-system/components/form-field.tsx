/**
 * A labelled input with an optional hint and error (UI-30: every input has a label). The error
 * replaces the hint under the input, as the account management mockups show. The caller links the
 * input to the text under it with `aria-describedby`, using {@link getFieldDescriptionId}.
 */
import { TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";

import { InlineMessage } from "@/design-system/components/inline-message";
import { FieldLabel } from "@/design-system/primitives/field-label";
import { Text } from "@/design-system/primitives/text";

/** Props of {@link FormField}. */
export type FormFieldProps = {
  /** The `id` of the input inside. */
  readonly inputId: string;
  readonly label: string;
  /** What the field expects, such as its limits. */
  readonly hint?: string | undefined;
  /** What is wrong with the value, after a check; it replaces the hint. */
  readonly error?: string | undefined;
  /** The input element. */
  readonly children: ReactNode;
};

/**
 * Choose the `aria-describedby` of the input of a {@link FormField}.
 *
 * @param field - The input's `id`, the hint, and the error of the field.
 * @returns The ID of the error, or else of the hint, or undefined when the field shows neither.
 */
export function getFieldDescriptionId(
  field: Pick<FormFieldProps, "inputId" | "hint" | "error">,
): string | undefined {
  if (field.error !== undefined) {
    return buildErrorId(field.inputId);
  }
  return field.hint === undefined ? undefined : buildHintId(field.inputId);
}

/**
 * Render a label, its input, and the hint or the error.
 *
 * @param props - The input's `id`, the label, the hint, the error, and the input.
 * @returns The field.
 */
export function FormField({ inputId, label, hint, error, children }: FormFieldProps) {
  return (
    <div className="flex flex-col gap-1">
      <FieldLabel htmlFor={inputId}>{label}</FieldLabel>
      {children}
      {error === undefined ? null : (
        <InlineMessage tone="danger" icon={TriangleAlert} role="alert" id={buildErrorId(inputId)}>
          {error}
        </InlineMessage>
      )}
      {error === undefined && hint !== undefined ? (
        <p id={buildHintId(inputId)}>
          <Text size="xs" tone="muted">
            {hint}
          </Text>
        </p>
      ) : null}
    </div>
  );
}

/**
 * Build the element ID of the error of a field.
 *
 * @param inputId - The `id` of the input.
 * @returns The ID.
 */
function buildErrorId(inputId: string): string {
  return `${inputId}-error`;
}

/**
 * Build the element ID of the hint of a field.
 *
 * @param inputId - The `id` of the input.
 * @returns The ID.
 */
function buildHintId(inputId: string): string {
  return `${inputId}-hint`;
}
