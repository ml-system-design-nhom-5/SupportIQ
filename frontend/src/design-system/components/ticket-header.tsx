/**
 * The ticket header (console UI design, Workspace regions): the ticket ID as the page heading, the
 * status, the handling mode, the order chip, the customer, and the time received. It spans the
 * middle and right columns of the workspace.
 */
import { User } from "lucide-react";
import type { ReactNode } from "react";

import { RelativeTime } from "@/design-system/components/relative-time";
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";
import { Icon } from "@/design-system/primitives/icon";
import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

/** Props of {@link TicketHeader}. */
export type TicketHeaderProps = {
  /** The ID of the heading, which takes the focus when the element that held it is gone. */
  readonly headingId: string;
  readonly ticketId: string;
  readonly status: StatusPresentation;
  readonly handlingMode: StatusPresentation;
  /** The order chip, or a line that says that no order is attached. */
  readonly order: ReactNode;
  readonly customerName: string;
  /** When the ticket was created, as an RFC 3339 timestamp. */
  readonly receivedAt: string;
};

/**
 * Render the ticket header.
 *
 * @param props - The heading ID, the ticket ID, the badges, the order, the customer, and the time
 *   received.
 * @returns The header row.
 */
export function TicketHeader({
  headingId,
  ticketId,
  status,
  handlingMode,
  order,
  customerName,
  receivedAt,
}: TicketHeaderProps) {
  return (
    <div className="flex items-center gap-3 border-b border-border bg-surface px-6 py-3">
      <h1
        id={headingId}
        tabIndex={-1}
        className="flex shrink-0 items-center gap-2 text-base font-semibold whitespace-nowrap text-text outline-none"
      >
        Ticket <span className="font-mono">{ticketId}</span>
      </h1>
      <StatusBadge presentation={status} />
      <StatusBadge presentation={handlingMode} />
      <span aria-hidden="true" className="h-6 border-l border-border" />
      <div className="flex min-w-0">{order}</div>
      <p className="ml-auto flex shrink-0 items-center gap-4 text-sm whitespace-nowrap text-text-muted">
        <span className="flex items-center gap-1">
          <Icon icon={User} />
          <VisuallyHidden>Customer: </VisuallyHidden>
          {customerName}
        </span>
        <span>
          Received <RelativeTime timestamp={receivedAt} />
        </span>
      </p>
    </div>
  );
}
