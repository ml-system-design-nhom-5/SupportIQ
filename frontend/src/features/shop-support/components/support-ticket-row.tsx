/**
 * One ticket on the Support screen: an excerpt of the message, the ticket ID, the order ID, the
 * time, and the status. The row opens the order page at that ticket (shop UI design, Screens).
 */
import {
  Identifier,
  presentationByShopTicketStatus,
  RelativeTimeText,
  RowListItem,
  StatusBadge,
  Text,
} from "@/design-system";
import { buildOrderPath } from "@/features/shop-orders";
import { buildTicketAnchorId, type ShopTicket } from "@/features/shop-support/model/ticket";

/** Props of {@link SupportTicketRow}. */
export type SupportTicketRowProps = {
  readonly ticket: ShopTicket;
};

/**
 * Render a ticket as a row of the Support list.
 *
 * @param props - The ticket.
 * @returns The list item.
 */
export function SupportTicketRow({ ticket }: SupportTicketRowProps) {
  return (
    <RowListItem
      to={buildOrderPath(ticket.orderId, buildTicketAnchorId(ticket.ticketId))}
      trailing={<StatusBadge presentation={presentationByShopTicketStatus[ticket.status]} />}
      trailingOnPhone="below"
    >
      <Text size="base" overflow="truncate">
        {ticket.message}
      </Text>
      <Text tone="muted">
        <Identifier size="xs">{ticket.ticketId}</Identifier> · Order{" "}
        <Identifier size="xs">{ticket.orderId}</Identifier> ·{" "}
        <RelativeTimeText timestamp={ticket.createdAt} />
      </Text>
    </RowListItem>
  );
}
