/**
 * A button that shows the chosen option and opens the list of options, on Radix DropdownMenu with a
 * radio group (UI-31; console UI design, Inbox: "A dropdown selects the status"). Enter, Space, or
 * the down arrow opens it, the arrow keys move between the options, Escape closes it, and the focus
 * returns to the button.
 */
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import { MENU_CONTENT_CLASSES, MENU_ITEM_CLASSES } from "@/design-system/primitives/menu-item";

/** One option of a {@link MenuSelect}. */
export type MenuSelectOption<Value extends string> = {
  readonly value: Value;
  readonly label: string;
};

/** Props of {@link MenuSelect}. */
export type MenuSelectProps<Value extends string> = {
  /** What is chosen, such as "Ticket status". The button's name is this label and the choice. */
  readonly label: string;
  /** The options, at least one, in the order of the list. */
  readonly options: readonly MenuSelectOption<Value>[];
  /** The chosen option: one of the values of `options`. */
  readonly value: Value;
  readonly onChange: (value: Value) => void;
};

/**
 * Render the button and its list of options.
 *
 * @param props - The label, the options, the chosen value, and the change handler.
 * @returns The button; the list opens in a portal.
 */
export function MenuSelect<Value extends string>({
  label,
  options,
  value,
  onChange,
}: MenuSelectProps<Value>) {
  const chosenLabel = options.find((option) => option.value === value)?.label ?? value;
  const handleValueChange = (nextValue: string) => {
    const chosen = options.find((option) => option.value === nextValue);
    if (chosen !== undefined) {
      onChange(chosen.value);
    }
  };
  return (
    // Not modal, as in the WAI-ARIA menu button pattern (axe aria-hidden-focus, UI-32).
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger
        aria-label={`${label}: ${chosenLabel}`}
        className={cn(
          "flex h-8 items-center gap-2 rounded-md border border-border-strong bg-surface px-3 text-sm font-medium text-text hover:bg-background",
          FOCUS_RING_CLASSES,
        )}
      >
        {chosenLabel}
        <Icon icon={ChevronDown} />
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="start"
          sideOffset={4}
          className={MENU_CONTENT_CLASSES}
        >
          <DropdownMenuPrimitive.Label className="p-2 text-xs text-text-muted">
            {label}
          </DropdownMenuPrimitive.Label>
          <DropdownMenuPrimitive.RadioGroup value={value} onValueChange={handleValueChange}>
            {options.map((option) => (
              <DropdownMenuPrimitive.RadioItem
                key={option.value}
                value={option.value}
                className={MENU_ITEM_CLASSES}
              >
                <span className="flex size-4 items-center justify-center">
                  <DropdownMenuPrimitive.ItemIndicator>
                    <Icon icon={Check} />
                  </DropdownMenuPrimitive.ItemIndicator>
                </span>
                {option.label}
              </DropdownMenuPrimitive.RadioItem>
            ))}
          </DropdownMenuPrimitive.RadioGroup>
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
