/**
 * One entry of the navigation in the app bar. The current page is marked with
 * `aria-current="page"` and the `background` role, so color is not the only signal (UI-11). The
 * router decides which entry is current, unless the area says it: an entry whose path holds
 * the paths of another entry, such as Tickets at `/console` above Reports at
 * `/console/reports`, cannot tell from the path alone.
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router";

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
  /**
   * Whether the item is the current page, which then replaces what the router decides, so
   * `isExactMatch` has no effect. Absent, the router decides from the path.
   */
  readonly isCurrent?: boolean;
  readonly children: ReactNode;
};

/**
 * Render a navigation entry.
 *
 * @param props - The path, the icon, the label, and how the current page is decided.
 * @returns The link, marked when its section is open.
 */
export function NavItem({ to, icon, isExactMatch = false, isCurrent, children }: NavItemProps) {
  const content = (
    <>
      <Icon icon={icon} />
      {children}
    </>
  );
  if (isCurrent !== undefined) {
    return (
      <Link
        to={to}
        aria-current={isCurrent ? "page" : undefined}
        className={navItemClasses(isCurrent)}
      >
        {content}
      </Link>
    );
  }
  return (
    <NavLink to={to} end={isExactMatch} className={({ isActive }) => navItemClasses(isActive)}>
      {content}
    </NavLink>
  );
}

/**
 * Build the classes of an entry.
 *
 * @param isCurrent - Whether the entry is the current page.
 * @returns The classes, with the `background` role on the current page.
 */
function navItemClasses(isCurrent: boolean): string {
  return cn(
    "flex items-center gap-2 rounded-md px-2 py-1 font-medium whitespace-nowrap sm:px-3",
    FOCUS_RING_CLASSES,
    isCurrent ? "bg-background text-text" : "text-text-muted hover:text-text",
  );
}
