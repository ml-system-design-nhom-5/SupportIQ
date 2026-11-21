/**
 * One ticket on the order page (shop UI design, Support for this order): its ID and status, the
 * customer's message on the right marked "You", and the reply on the left marked "Reply from
 * support", or a line that says that a person replies. Text is rendered as text (SEC-22).
 */
import { Clock } from "lucide-react";

import { InlineMessage } from "@/design-system/components/inline-message";
import { MessageBubble } from "@/design-system/components/message-bubble";
import { RelativeTime } from "@/design-system/components/relative-time";
import { StatusBadge } from "@/design-system/components/status-badge";
import type { StatusPresentation } from "@/design-system/components/status-presentations";

/** The reply that staff sent. */
export type TicketItemReply = {
  readonly body: string;
  /** When staff sent it, as an RFC 3339 timestamp. */
  readonly sentAt: string;
};

/** Props of {@link TicketItem}. */
export type TicketItemProps = {
  /** The element ID that a link from Support scrolls to. */
  readonly anchorId: string;
  readonly ticketId: string;
  readonly status: StatusPresentation;
  readonly message: string;
  /** When the customer sent the message, as an RFC 3339 timestamp. */
  readonly createdAt: string;
  /** The reply; absent until staff send it. */
  readonly reply?: TicketItemReply;
};

/**
 * Render a ticket as an item of the order's ticket list.
 *
 * @param props - The ticket's anchor, ID, status, message, time, and reply.
 * @returns The list item.
 */
export function TicketItem({
  anchorId,
  ticketId,
  status,
  message,
  createdAt,
  reply,
}: TicketItemProps) {
  return (
    <li id={anchorId} tabIndex={-1} className="flex scroll-mt-4 flex-col gap-2">
      <p className="flex items-center justify-end gap-2">
        <span className="min-w-0 font-mono text-xs text-text-muted">{ticketId}</span>
        <StatusBadge presentation={status} />
      </p>
      <MessageBubble
        author="customer"
        header={
          <>
            <span className="font-medium text-text">You</span> ·{" "}
            <RelativeTime timestamp={createdAt} />
          </>
        }
        text={message}
      />
      {reply === undefined ? (
        <InlineMessage tone="muted" icon={Clock}>
          No reply yet. A person from our support team replies here.
        </InlineMessage>
      ) : (
        <MessageBubble
          author="support"
          header={
            <>
              <span className="font-medium text-text">Reply from support</span> ·{" "}
              <RelativeTime timestamp={reply.sentAt} />
            </>
          }
          text={reply.body}
        />
      )}
    </li>
  );
}
