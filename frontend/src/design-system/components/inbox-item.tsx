/**
 * One ticket of the inbox (console UI design, Inbox): a link that opens the ticket with one click.
 * It shows the ticket ID, the time received, the customer, the message excerpt, the intent line,
 * a status badge, the authority flag, and who opened it. The open ticket is marked with
 * `aria-current="page"` and a bar in the `primary` role, so color is not the only signal (UI-11).
 * Text is rendered as text (SEC-22).
 */
import { User } from "lucide-react";
import type { ReactNode } from "react";
import { NavLink } from "react-router";

import { RelativeTimeText } from "@/design-system/components/relative-time-text";
import { StatusBadge } from "@/design-system/components/status-badge";
import {
  authorityRequiredPresentation,
  type StatusPresentation,
} from "@/design-system/components/status-presentations";
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
  /** The predicted intent with its confidence, or a line that says why there is none. */
  readonly intentLine: ReactNode;
  readonly status: StatusPresentation;
  readonly isAuthorityRequired: boolean;
  /** When a person first opened the ticket; absent until then. */
  readonly openedAt?: string;
};

/**
 * Render the ticket as an item of the inbox.
 *
 * @param props - The path and the facts of the ticket.
 * @returns The list item with its link.
 */
export function InboxItem({
  to,
  ticketId,
  createdAt,
  customerName,
  excerpt,
  intentLine,
  status,
  isAuthorityRequired,
  openedAt,
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
        <span className="flex items-center gap-2 text-text">{intentLine}</span>
        <span className="flex flex-wrap gap-2">
          <StatusBadge presentation={status} />
          {isAuthorityRequired ? (
            <StatusBadge presentation={authorityRequiredPresentation} />
          ) : null}
        </span>
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
