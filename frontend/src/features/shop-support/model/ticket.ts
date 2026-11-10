/**
 * The view models of the customer's tickets and their mappings from the contract (TS-09). A
 * ticket holds one message and, once staff sent it, one reply. It never holds AI output
 * (ADR-0013).
 */
import type { ShopTicketStatusName } from "@/design-system";
import { requireMembers } from "@/features/backend-requests";
import type {
  ShopTicketContract,
  ShopTicketPageContract,
} from "@/features/shop-support/api/contract-types";

/** The reply that staff sent. Confidential: shown, never logged. */
export type ShopReply = {
  readonly body: string;
  readonly sentAt: string;
};

/** A ticket as the customer sees it. */
export type ShopTicket = {
  readonly ticketId: string;
  readonly orderId: string;
  /** The customer's message, exactly as written. Confidential: shown, never logged. */
  readonly message: string;
  readonly createdAt: string;
  readonly status: ShopTicketStatusName;
  /** Absent until staff send the reply. */
  readonly reply?: ShopReply;
};

/** One page of the customer's tickets (CON-14). */
export type ShopTicketPage = {
  readonly tickets: readonly ShopTicket[];
  readonly nextCursor?: string;
};

/**
 * Map a ticket status from `backend`.
 *
 * @param value - The `customer_status` of a `ShopTicketView`.
 * @returns `replied`, or `received` for any other value, as the contract tells consumers to show
 *   an unknown value (`ShopTicketStatus`, CON-22).
 */
export function toShopTicketStatus(value: string): ShopTicketStatusName {
  return value === "replied" ? "replied" : "received";
}

/**
 * Map a contract ticket.
 *
 * @param ticket - A `ShopTicketView`.
 * @returns The view model.
 */
export function toShopTicket(ticket: ShopTicketContract): ShopTicket {
  requireMembers(ticket, ["ticket_id", "order_id", "message", "created_at", "customer_status"]);
  const mapped: ShopTicket = {
    ticketId: ticket.ticket_id,
    orderId: ticket.order_id,
    message: ticket.message,
    createdAt: ticket.created_at,
    status: toShopTicketStatus(ticket.customer_status),
  };
  if (ticket.reply === undefined) {
    return mapped;
  }
  requireMembers(ticket.reply, ["body", "sent_at"]);
  return { ...mapped, reply: { body: ticket.reply.body, sentAt: ticket.reply.sent_at } };
}

/**
 * Map a page of `listShopTickets`.
 *
 * @param page - A `ShopTicketPage`.
 * @returns The tickets and the cursor of the next page.
 */
export function toShopTicketPage(page: ShopTicketPageContract): ShopTicketPage {
  const tickets = page.items.map(toShopTicket);
  return page.next_cursor === undefined ? { tickets } : { tickets, nextCursor: page.next_cursor };
}

/**
 * Build the element ID of a ticket on its order page, which links from Support scroll to.
 *
 * @param ticketId - The `ticket_id`.
 * @returns For example `ticket-TCK-1042`.
 */
export function buildTicketAnchorId(ticketId: string): string {
  return `ticket-${ticketId}`;
}

/**
 * Read the element ID that the fragment of an address names.
 *
 * @param hash - The fragment with its leading `#`, or an empty string.
 * @returns The element ID, or undefined when the fragment is empty or malformed, because such an
 *   address names no ticket.
 */
export function readAnchorIdOfHash(hash: string): string | undefined {
  if (hash.length <= 1) {
    return undefined;
  }
  try {
    return decodeURIComponent(hash.slice(1));
  } catch (error) {
    if (error instanceof URIError) {
      return undefined;
    }
    throw error;
  }
}
