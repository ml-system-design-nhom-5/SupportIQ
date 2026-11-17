/**
 * A checkbox with its label and a hint that says what the choice means: a native input styled
 * with tokens, so it needs no package (account management design, Dependencies of `frontend`).
 */
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Text } from "@/design-system/primitives/text";

/** The classes of a checkbox input, which the warning list shares (CODE-48). */
export const CHECKBOX_INPUT_CLASSES = cn("size-4 shrink-0 accent-primary", FOCUS_RING_CLASSES);

/** Props of {@link Checkbox}. */
export type CheckboxProps = {
  readonly id: string;
  readonly label: string;
  /** What the choice means, under the label. */
  readonly hint: string;
  readonly isChecked: boolean;
  readonly onCheckedChange: (isChecked: boolean) => void;
};

/**
 * Render a checkbox.
 *
 * @param props - The `id`, the label, the hint, the state, and the change handler.
 * @returns The checkbox with its label and hint.
 */
export function Checkbox({ id, label, hint, isChecked, onCheckedChange }: CheckboxProps) {
  const hintId = `${id}-hint`;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <input
          id={id}
          type="checkbox"
          checked={isChecked}
          aria-describedby={hintId}
          className={CHECKBOX_INPUT_CLASSES}
          onChange={(event) => {
            onCheckedChange(event.target.checked);
          }}
        />
        <label htmlFor={id} className="text-sm text-text">
          {label}
        </label>
      </div>
      <p id={hintId}>
        <Text size="xs" tone="muted">
          {hint}
        </Text>
      </p>
    </div>
  );
}
