/**
 * One ticket of the inbox, from its view model (console UI design, Inbox).
 */
import {
  ConfidenceMeter,
  InboxItem,
  presentationByAiStatus,
  presentationByConsoleTicketStatus,
  type StatusPresentation,
  Text,
} from "@/design-system";
import { buildTicketPath } from "@/features/console-tickets/model/console-paths";
import type { QueueStatus } from "@/features/console-tickets/model/queue";
import type { SummaryBadge, TicketSummary } from "@/features/console-tickets/model/ticket-summary";

/** Props of {@link InboxTicket}. */
type InboxTicketProps = {
  readonly ticket: TicketSummary;
  /** The queue that the inbox shows, which the link keeps. */
  readonly queueStatus: QueueStatus;
};

/**
 * Render a ticket of the inbox.
 *
 * @param props - The ticket and the queue.
 * @returns The inbox item.
 */
export function InboxTicket({ ticket, queueStatus }: InboxTicketProps) {
  const intent = ticket.intent;
  return (
    <InboxItem
      to={buildTicketPath(ticket.ticketId, queueStatus)}
      ticketId={ticket.ticketId}
      createdAt={ticket.createdAt}
      customerName={ticket.customerName}
      excerpt={ticket.excerpt}
      intentLine={
        intent.kind === "predicted" ? (
          <>
            {intent.name}
            <ConfidenceMeter band={intent.band} probability={intent.probability} />
          </>
        ) : (
          <Text tone="muted">{intent.text}</Text>
        )
      }
      status={getBadgePresentation(ticket.badge)}
      isAuthorityRequired={ticket.isAuthorityRequired}
      {...(ticket.openedAt === undefined ? {} : { openedAt: ticket.openedAt })}
    />
  );
}

/**
 * Choose the presentation of the badge of a ticket (UI-12).
 *
 * @param badge - The AI status or the ticket status.
 * @returns The presentation.
 */
function getBadgePresentation(badge: SummaryBadge): StatusPresentation {
  return badge.kind === "ai"
    ? presentationByAiStatus[badge.status]
    : presentationByConsoleTicketStatus[badge.status];
}
