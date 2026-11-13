/**
 * The account menu of every area (account management design, Account menu), on Radix DropdownMenu
 * (UI-31). Enter, Space, or the down arrow opens it, the arrow keys move between its items, Escape
 * closes it, and the focus returns to the trigger. The trigger shows the person icon, the display
 * name, the role label, and a chevron; in the shop at phone width, the text is visually hidden, so
 * the accessible name stays the same. The display name is Confidential: it is only rendered, never
 * logged (SEC-01).
 */
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { ChevronDown, KeyRound, LogOut, User } from "lucide-react";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";
import { MENU_CONTENT_CLASSES, MENU_ITEM_CLASSES } from "@/design-system/primitives/menu-item";

/** `shop` hides the trigger text at phone width; `console` is the desktop bar (UI-33). */
export type AccountMenuVariant = "shop" | "console";

/** Props of {@link AccountMenu}. */
export type AccountMenuProps = {
  readonly variant: AccountMenuVariant;
  readonly displayName: string;
  /** The role label, for example "Staff". */
  readonly roleLabel: string;
  /** True while sign-out waits for `backend`: Sign out is disabled, so it is sent once. */
  readonly isSigningOut: boolean;
  readonly onChangePassword: () => void;
  readonly onSignOut: () => void;
};

/**
 * Render the menu button and its menu.
 *
 * @param props - The variant, the account, the sign-out state, and the handlers of the items.
 * @returns The trigger; the menu opens in a portal.
 */
export function AccountMenu({
  variant,
  displayName,
  roleLabel,
  isSigningOut,
  onChangePassword,
  onSignOut,
}: AccountMenuProps) {
  return (
    // Not modal, as in the WAI-ARIA menu button pattern: the page is never hidden from assistive
    // technology while it holds the focusable trigger (axe aria-hidden-focus, UI-32).
    <DropdownMenuPrimitive.Root modal={false}>
      <DropdownMenuPrimitive.Trigger
        // The name repeats the visible text, which is two flex items, so it reads the same in every
        // browser and at phone width, where the text is hidden (WCAG 2.5.3).
        aria-label={`${displayName} · ${roleLabel}`}
        className={cn(
          "flex h-8 min-w-0 items-center gap-2 rounded-md border border-transparent px-2 text-text-muted hover:bg-background aria-expanded:border-border-strong aria-expanded:bg-background",
          FOCUS_RING_CLASSES,
        )}
      >
        <Icon icon={User} />
        <span
          className={cn("flex min-w-0 items-center gap-1", variant === "shop" && "max-sm:sr-only")}
        >
          <span className="truncate font-medium text-text">{displayName}</span>
          <span className="whitespace-nowrap">· {roleLabel}</span>
        </span>
        <Icon icon={ChevronDown} />
      </DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          align="end"
          sideOffset={4}
          className={cn(MENU_CONTENT_CLASSES, "max-w-menu")}
        >
          <DropdownMenuPrimitive.Label className="flex flex-col p-2">
            <span className="font-semibold wrap-anywhere text-text">{displayName}</span>
            <span className="text-text-muted">{roleLabel}</span>
          </DropdownMenuPrimitive.Label>
          <DropdownMenuPrimitive.Separator className="my-1 border-t border-border" />
          <DropdownMenuPrimitive.Item className={MENU_ITEM_CLASSES} onSelect={onChangePassword}>
            <Icon icon={KeyRound} />
            Change password
          </DropdownMenuPrimitive.Item>
          <DropdownMenuPrimitive.Item
            className={MENU_ITEM_CLASSES}
            disabled={isSigningOut}
            onSelect={onSignOut}
          >
            <Icon icon={LogOut} />
            {isSigningOut ? "Signing out…" : "Sign out"}
          </DropdownMenuPrimitive.Item>
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
