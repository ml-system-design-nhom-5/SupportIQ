/**
 * A labelled group of chips that each turn on or off, such as the staff reason codes of a rejected
 * draft (console UI design, Actions, state-rejected.png: "Why did you reject it?"). The group is a
 * `fieldset` named by its visible legend. Each chip is a toggle button, so its state is announced
 * as pressed; a chip that is on has the dark fill of the `text` role, so its state does not rest on
 * hue alone (UI-11).
 */
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
};

/**
 * Render the group.
 *
 * @param props - The label, the chips, the chips that are on, and the toggle handler.
 * @returns The group of toggle buttons.
 */
export function ToggleChipGroup<Value extends string>({
  label,
  options,
  selected,
  onToggle,
}: ToggleChipGroupProps<Value>) {
  return (
    <fieldset className="flex min-w-0 flex-col">
      <legend className="mb-2 text-sm font-medium text-text">{label}</legend>
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
    </fieldset>
  );
}
