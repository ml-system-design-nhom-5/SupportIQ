/**
 * The action bar at the bottom of the reply area (UI-16; console UI design, Actions and placement
 * rule 2). It never moves: the secondary actions on the left, then More for the actions that sit in
 * a menu, such as Submit for approval when authority is not required, and the primary action on
 * the right. When an action is disabled, one line above the buttons says why. More opens a menu on
 * Radix DropdownMenu (UI-31): Enter, Space, or the down arrow opens it, the arrow keys move between
 * its items, Escape closes it, and the focus returns to More. Each item can say what it does on a
 * second line, which is then part of its name, so the name holds all of its visible text (WCAG
 * 2.5.3). More is absent without items and disabled when every item is. The bar sticks to the
 * bottom of the scrolling column, so it stays visible while the reply area scrolls (placement
 * rule 4).
 */
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { Ellipsis, Info, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { InlineMessage } from "@/design-system/components/inline-message";
import { buttonVariants } from "@/design-system/primitives/button";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import { MENU_CONTENT_CLASSES, MENU_ITEM_CLASSES } from "@/design-system/primitives/menu-item";

/** One action in the More menu. */
export type ActionMenuItem = {
  readonly icon: LucideIcon;
  /** A verb that names the result, such as "Submit for approval" (UI-27); unique in the menu. */
  readonly label: string;
  /** What happens, on a second line, such as "A manager sends the reply". */
  readonly description?: string;
  /** True when the action is not available now; the reason line of the bar says why. */
  readonly isDisabled?: boolean;
  readonly onSelect: () => void;
};

/** Props of {@link ActionBar}. */
export type ActionBarProps = {
  /** Why an action is disabled, such as "Acknowledge 1 warning to send the reply." */
  readonly reason?: string;
  /** The secondary actions, such as Edit draft, Reject draft, and Escalate ticket. */
  readonly actions: ReactNode;
  /** The actions of the More menu; without any, there is no More button. */
  readonly moreItems?: readonly ActionMenuItem[];
  /** The main action of the view, such as Send reply. */
  readonly primaryAction: ReactNode;
};

/**
 * Render the action bar.
 *
 * @param props - The reason line, the secondary actions, the items of More, and the main action.
 * @returns The bar; the More menu opens in a portal.
 */
export function ActionBar({ reason, actions, moreItems = [], primaryAction }: ActionBarProps) {
  return (
    <div className="sticky bottom-0 mt-auto flex flex-col gap-2 border-t border-border bg-surface px-4 py-3">
      {reason === undefined ? null : (
        <InlineMessage tone="muted" icon={Info}>
          {reason}
        </InlineMessage>
      )}
      <div className="flex flex-wrap items-center gap-2">
        {actions}
        {moreItems.length === 0 ? null : <MoreMenu items={moreItems} />}
        <div className="ml-auto">{primaryAction}</div>
      </div>
    </div>
  );
}

/** Props of {@link MoreMenu}. */
type MoreMenuProps = {
  readonly items: readonly ActionMenuItem[];
};

/**
 * Render More and its menu.
 *
 * @param props - The items, at least one.
 * @returns The icon button; the menu opens in a portal.
 */
function MoreMenu({ items }: MoreMenuProps) {
  const isEveryItemDisabled = items.every((item) => item.isDisabled === true);
  return (
    // Not modal, as in the WAI-ARIA menu button pattern (axe aria-hidden-focus, UI-32).
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger
        aria-label="More actions"
        disabled={isEveryItemDisabled}
        className={cn(
          buttonVariants({ variant: "secondary", size: "md" }),
          "aria-expanded:bg-background",
          FOCUS_RING_CLASSES,
        )}
      >
        <Icon icon={Ellipsis} />
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          side="top"
          align="end"
          sideOffset={4}
          className={cn(MENU_CONTENT_CLASSES, "max-w-menu")}
        >
          {items.map((item) => (
            <MoreMenuItem key={item.label} item={item} />
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}

/** Props of {@link MoreMenuItem}. */
type MoreMenuItemProps = {
  readonly item: ActionMenuItem;
};

/**
 * Render one item of the More menu: the label, then the description on a second line.
 *
 * @param props - The item.
 * @returns The menu item, named by its label and its description.
 */
function MoreMenuItem({ item }: MoreMenuItemProps) {
  return (
    <DropdownMenuPrimitive.Item
      disabled={item.isDisabled ?? false}
      className={cn(MENU_ITEM_CLASSES, "items-start")}
      onSelect={item.onSelect}
    >
      <Icon icon={item.icon} />
      <span className="flex min-w-0 flex-col gap-1">
        {/* The space keeps the two lines apart in the name of the item. */}
        <span>{item.label}</span>{" "}
        {item.description === undefined ? null : (
          <span className="text-xs font-normal text-text-muted">{item.description}</span>
        )}
      </span>
    </DropdownMenuPrimitive.Item>
  );
}
