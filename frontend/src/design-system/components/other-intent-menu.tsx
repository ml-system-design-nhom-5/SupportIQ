/**
 * Other intent (UI-22, UI-42; console UI design, Workspace regions and States): a menu of the other
 * intents that staff can choose, on Radix DropdownMenu (UI-31). The intent strip offers it next to
 * its candidates, and the choice of an intent below them.
 */
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { ChevronRight } from "lucide-react";

import { Button } from "@/design-system/primitives/button";
import { cn } from "@/design-system/primitives/class-names";
import { Icon } from "@/design-system/primitives/icon";
import { MENU_CONTENT_CLASSES, MENU_ITEM_CLASSES } from "@/design-system/primitives/menu-item";

/** How staff use an intent that the intent strip or the choice offers (UI-22, UI-42). */
export type IntentUse<Value extends string = string> = {
  /**
   * True while a correction is sending. The buttons then read as disabled and ignore activation,
   * so one correction is sent at a time, and they keep the focus (UI-30).
   */
  readonly isSending: boolean;
  readonly onUseIntent: (value: Value) => void;
};

/** An intent of the Other intent menu. */
export type IntentOption<Value extends string = string> = {
  readonly value: Value;
  readonly name: string;
};

/** How staff correct the intent from the strip (UI-22), or choose one from the choice (UI-42). */
export type IntentCorrection<Value extends string = string> = IntentUse<Value> & {
  /** The intents that Other intent lists, in the order of the menu. */
  readonly otherIntents: readonly IntentOption<Value>[];
  /**
   * The ID of the Other intent button, which a script moves the focus to, such as when the
   * element that held the focus is gone (UI-30). The menu stays named by the button.
   */
  readonly otherIntentId?: string;
};

/** Props of {@link OtherIntentMenu}. */
type OtherIntentMenuProps<Value extends string> = {
  readonly correction: IntentCorrection<Value>;
};

/**
 * Render Other intent: a button that opens the menu of the other intents. Enter, Space, or the
 * down arrow opens it, the arrow keys and typing move between the intents, Escape closes it, and
 * the focus returns to the button. The menu opens beside the button and stays within the height
 * of the window, where its list scrolls. Its items are disabled while a correction is sending.
 * The button takes the `otherIntentId` of the correction, and the menu is then labelled by that ID
 * instead of the one that Radix gives the button, so it keeps its name.
 *
 * @param props - The correction.
 * @returns The button; the menu opens in a portal.
 */
export function OtherIntentMenu<Value extends string>({ correction }: OtherIntentMenuProps<Value>) {
  const { otherIntentId } = correction;
  return (
    // Not modal, as in the WAI-ARIA menu button pattern (axe aria-hidden-focus, UI-32).
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger
        asChild
        {...(otherIntentId === undefined ? {} : { id: otherIntentId })}
      >
        <Button size="sm" variant="ghost">
          Other intent
          <Icon icon={ChevronRight} />
        </Button>
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          side="right"
          align="start"
          sideOffset={4}
          className={cn(MENU_CONTENT_CLASSES, "max-h-screen overflow-y-auto")}
          {...(otherIntentId === undefined ? {} : { "aria-labelledby": otherIntentId })}
        >
          {correction.otherIntents.map((option) => (
            <DropdownMenuPrimitive.Item
              key={option.value}
              className={MENU_ITEM_CLASSES}
              disabled={correction.isSending}
              onSelect={() => {
                correction.onUseIntent(option.value);
              }}
            >
              {option.name}
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
