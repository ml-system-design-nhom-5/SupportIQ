/**
 * One entry of the navigation in the app bar. The current page is marked with
 * `aria-current="page"` and the `background` role, so color is not the only signal (UI-11).
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link NavItem}. */
export type NavItemProps = {
  /** The app path of the section. */
  readonly to: string;
  readonly icon: LucideIcon;
  /** Marks the item current only on its exact path, not on the paths below it. */
  readonly isExactMatch?: boolean;
  readonly children: ReactNode;
};

/**
 * Render a navigation entry.
 *
 * @param props - The path, the icon, and the label.
 * @returns The link, marked when its section is open.
 */
export function NavItem({ to, icon, isExactMatch = false, children }: NavItemProps) {
  return (
    <NavLink
      to={to}
      end={isExactMatch}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 rounded-md px-2 py-1 font-medium whitespace-nowrap sm:px-3",
          FOCUS_RING_CLASSES,
          isActive ? "bg-background text-text" : "text-text-muted hover:text-text",
        )
      }
    >
      <Icon icon={icon} />
      {children}
    </NavLink>
  );
}
