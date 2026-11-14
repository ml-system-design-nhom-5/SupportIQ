/**
 * A labelled group of chips that each turn on or off, such as the staff reason codes of a rejected
 * draft (console UI design, Actions, state-rejected.png: "Why did you reject it?"). The group is a
 * `fieldset` named by its legend, which a dialog whose text already asks the question hides
 * (dialog-escalate.png). Each chip is a toggle button, so its state is announced as pressed; a chip
 * that is on has the dark fill of the `text` role, so its state does not rest on hue alone (UI-11).
 * An error shows under the chips and describes the group, as {@link FormField} does for an input.
 */
import { TriangleAlert } from "lucide-react";
import { useId } from "react";

import { InlineMessage } from "@/design-system/components/inline-message";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** One chip of a {@link ToggleChipGroup}. */
export type ToggleChipOption<Value extends string> = {
  readonly value: Value;
  readonly label: string;
};

/** Props of {@link ToggleChipGroup}. */
export type ToggleChipGroupProps<Value extends string> = {
  /** The question that the chips answer; it names the group. */
  readonly label: string;
  /** The chips, in the order shown. */
  readonly options: readonly ToggleChipOption<Value>[];
  /** The values of the chips that are on. */
  readonly selected: ReadonlySet<Value>;
  /** Called with the value of a chip that staff turn on or off. */
  readonly onToggle: (value: Value) => void;
  /** `hidden` keeps the label for assistive technology only; `visible` by default. */
  readonly labelVisibility?: "visible" | "hidden";
  /** What the choice still needs, such as "Choose at least one reason."; absent when nothing. */
  readonly error?: string;
};

/**
 * Render the group.
 *
 * @param props - The label and whether it shows, the chips, the chips that are on, the toggle
 *   handler, and the error.
 * @returns The group of toggle buttons.
 */
export function ToggleChipGroup<Value extends string>({
  label,
  options,
  selected,
  onToggle,
  labelVisibility = "visible",
  error,
}: ToggleChipGroupProps<Value>) {
  const errorId = useId();
  return (
    <fieldset
      className="flex min-w-0 flex-col gap-2"
      aria-describedby={error === undefined ? undefined : errorId}
    >
      <legend
        className={labelVisibility === "hidden" ? "sr-only" : "mb-2 text-sm font-medium text-text"}
      >
        {label}
      </legend>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const isSelected = selected.has(option.value);
          return (
            <button
              key={option.value}
              type="button"
              aria-pressed={isSelected}
              className={cn(
                "inline-flex h-6 items-center rounded-sm border px-2 text-sm whitespace-nowrap transition-colors duration-100",
                isSelected
                  ? "border-text bg-text text-text-inverse"
                  : "border-border bg-background text-text hover:border-border-strong",
                FOCUS_RING_CLASSES,
              )}
              onClick={() => {
                onToggle(option.value);
              }}
            >
              {option.label}
            </button>
          );
        })}
      </div>
      {error === undefined ? null : (
        <InlineMessage tone="danger" icon={TriangleAlert} role="alert" id={errorId}>
          {error}
        </InlineMessage>
      )}
    </fieldset>
  );
}
