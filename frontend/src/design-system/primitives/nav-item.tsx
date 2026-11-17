/**
 * One entry of the navigation in the app bar. The current page is marked with
 * `aria-current="page"` and the `background` role, so color is not the only signal (UI-11). By
 * default, the router decides which entry is current from its path and the paths below it. An
 * entry can ask the router for its exact path only, or let the area decide: an entry whose path
 * holds the paths of another entry, such as Tickets at `/console` above Reports at
 * `/console/reports`, cannot tell from the path alone. One prop holds that choice, so two ways to
 * decide can never be set at once (CODE-29).
 */
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink } from "react-router";

import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** How a navigation entry knows that its page is open. */
export type NavItemCurrent =
  | { readonly by: "path" } // the router: its path and the paths below it (the default)
  | { readonly by: "exact-path" } // the router: its exact path only
  | { readonly by: "area"; readonly isCurrent: boolean }; // the area decides

/** The default of {@link NavItemProps.current}. */
const currentByPath: NavItemCurrent = { by: "path" };

/** Props of {@link NavItem}. */
export type NavItemProps = {
  /** The app path of the section. */
  readonly to: string;
  readonly icon: LucideIcon;
  /** How the entry knows that its page is open; `{ by: "path" }` by default. */
  readonly current?: NavItemCurrent;
  readonly children: ReactNode;
};

/**
 * Render a navigation entry.
 *
 * @param props - The path, the icon, the label, and how the current page is decided.
 * @returns The link, marked when its section is open.
 */
export function NavItem({ to, icon, current = currentByPath, children }: NavItemProps) {
  const content = (
    <>
      <Icon icon={icon} />
      {children}
    </>
  );
  if (current.by === "area") {
    return (
      <Link
        to={to}
        aria-current={current.isCurrent ? "page" : undefined}
        className={navItemClasses(current.isCurrent)}
      >
        {content}
      </Link>
    );
  }
  return (
    <NavLink
      to={to}
      end={current.by === "exact-path"}
      className={({ isActive }) => navItemClasses(isActive)}
    >
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
