/**
 * A group of radio buttons under a legend: native inputs styled with tokens, so it needs no package
 * (account management design, Dependencies of `frontend`). The arrow keys move between the options,
 * as the browser does for radio buttons with one name.
 */
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** One option of a {@link RadioGroup}. */
export type RadioOption<Value extends string> = {
  readonly value: Value;
  readonly label: string;
};

/** Props of {@link RadioGroup}. */
export type RadioGroupProps<Value extends string> = {
  /** The `name` of the radio buttons, unique in the form. */
  readonly name: string;
  /** Names the group, as the label of a field does. */
  readonly legend: string;
  readonly options: readonly RadioOption<Value>[];
  readonly value: Value;
  readonly onValueChange: (value: Value) => void;
};

/**
 * Render the radio group.
 *
 * @param props - The name, the legend, the options, the chosen value, and the change handler.
 * @returns The fieldset with one radio button per option.
 */
export function RadioGroup<Value extends string>({
  name,
  legend,
  options,
  value,
  onValueChange,
}: RadioGroupProps<Value>) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="mb-1 text-sm font-medium text-text">{legend}</legend>
      <div className="flex flex-wrap gap-4">
        {options.map((option) => (
          <label
            key={option.value}
            className="flex items-center gap-2 text-sm font-medium text-text"
          >
            <input
              type="radio"
              name={name}
              value={option.value}
              checked={option.value === value}
              className={cn("size-4 shrink-0 accent-primary", FOCUS_RING_CLASSES)}
              onChange={() => {
                onValueChange(option.value);
              }}
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}
