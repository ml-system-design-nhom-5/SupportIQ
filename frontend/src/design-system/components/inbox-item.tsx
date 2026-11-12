/**
 * One ticket of the inbox (console UI design, Inbox): a link that opens the ticket with one click.
 * It shows the ticket ID, the time received, the customer, the message excerpt, its details, and
 * who opened it. The details are the intent line, a row, and the status badge with the authority
 * flag, a cluster. The open ticket is marked with
 * `aria-current="page"` and a bar in the `primary` role, so color is not the only signal (UI-11).
 * Text is rendered as text (SEC-22).
 */
import { User } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router";

import { RelativeTimeText } from "@/design-system/components/relative-time-text";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link InboxItem}. */
export type InboxItemProps = {
  /** The app path of the ticket workspace. */
  readonly to: string;
  readonly ticketId: string;
  /** When the customer sent the message, as an RFC 3339 timestamp. */
  readonly createdAt: string;
  readonly customerName: string;
  readonly excerpt: string;
  /** When a person first opened the ticket; absent until then. */
  readonly openedAt?: string;
  /**
   * The details under the excerpt: the predicted intent with its confidence, or a line that says
   * why there is none, then the badges.
   */
  readonly children: ReactNode;
};

/**
 * Render the ticket as an item of the inbox.
 *
 * @param props - The path, the facts of the ticket, and its details.
 * @returns The list item with its link.
 */
export function InboxItem({
  to,
  ticketId,
  createdAt,
  customerName,
  excerpt,
  openedAt,
  children,
}: InboxItemProps) {
  return (
    <li className="flex flex-col">
      <NavLink
        to={to}
        className={({ isActive }) =>
          cn(
            "flex flex-col gap-1 border-b border-l-4 border-b-border px-4 py-3 text-sm",
            FOCUS_RING_CLASSES,
            "focus-visible:-outline-offset-2",
            isActive
              ? "border-l-primary bg-info-subtle"
              : "border-l-transparent hover:bg-background",
          )
        }
      >
        <span className="flex items-baseline gap-2">
          <span className="font-mono text-text">{ticketId}</span>
          <span className="text-xs text-text-muted">
            <RelativeTimeText timestamp={createdAt} />
          </span>
        </span>
        <span className="font-semibold text-text">{customerName}</span>
        <span className="truncate text-text-muted">{excerpt}</span>
        {children}
        {openedAt === undefined ? null : (
          <span className="flex items-center gap-1 text-xs text-text-muted">
            <Icon icon={User} />
            Opened <RelativeTimeText timestamp={openedAt} />
          </span>
        )}
      </NavLink>
    </li>
  );
}
