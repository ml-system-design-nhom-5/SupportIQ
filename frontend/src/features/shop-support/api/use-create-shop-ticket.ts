/**
 * Write to support about an order (`createShopTicket`). The `Idempotency-Key` belongs to the
 * message: automatic retries reuse it, and so does sending the same text again after a failure, so
 * neither creates a second ticket (TS-29, ERR-15, shop UI design, Flow).
 */
import {
  type InfiniteData,
  type QueryClient,
  useMutation,
  type UseMutationResult,
  useQueryClient,
} from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import {
  buildIdempotentWriteKey,
  requestData,
  useWriteAttemptSender,
} from "@/features/backend-requests";
import { supportQueryKeys } from "@/features/shop-support/api/support-query-keys";
import {
  type ShopTicket,
  type ShopTicketPage,
  toShopTicket,
} from "@/features/shop-support/model/ticket";

/** One Send message: the text and its key. */
export type NewShopMessage = {
  readonly message: string;
  /** Stays until the send succeeds or the text changes (shop UI design, Flow). */
  readonly idempotencyKey: string;
};

/** The data of a cached ticket list. */
type TicketListData = InfiniteData<ShopTicketPage, string | undefined>;

/**
 * Create a ticket about an order. On success the ticket shows at once, and every ticket list is
 * loaded again, so Support shows it too.
 *
 * @param orderId - The order.
 * @returns The mutation; its key gives it the retry policy of idempotent writes.
 */
export function useCreateShopTicket(
  orderId: string,
): UseMutationResult<ShopTicket, Error, NewShopMessage> {
  const client = useBackendClient();
  const queryClient = useQueryClient();
  const sendAttempt = useWriteAttemptSender();
  return useMutation({
    mutationKey: buildIdempotentWriteKey("createShopTicket"),
    mutationFn: (newMessage: NewShopMessage) =>
      sendAttempt(newMessage.idempotencyKey, () => createShopTicket(client, orderId, newMessage)),
    onSuccess: (ticket) => {
      addTicketToOrderList(queryClient, ticket);
      void queryClient.invalidateQueries({ queryKey: supportQueryKeys.ticketLists() });
    },
  });
}

/**
 * Send the message.
 *
 * @param client - The backend client.
 * @param orderId - The order that the message is about.
 * @param newMessage - The text and the key.
 * @returns The created ticket, or the original one for a retry with the same key.
 */
function createShopTicket(
  client: BackendClient,
  orderId: string,
  newMessage: NewShopMessage,
): Promise<ShopTicket> {
  return requestData(
    () =>
      client.POST("/v1/shop/tickets", {
        params: { header: { "Idempotency-Key": newMessage.idempotencyKey } },
        body: { order_id: orderId, message: newMessage.message },
      }),
    toShopTicket,
  );
}

/**
 * Show the new ticket at once in the cached list of its order, before the list loads again.
 *
 * @param queryClient - The query client.
 * @param ticket - The created ticket.
 */
function addTicketToOrderList(queryClient: QueryClient, ticket: ShopTicket): void {
  queryClient.setQueryData<TicketListData>(
    supportQueryKeys.ticketsOfOrder(ticket.orderId),
    (cachedTickets) => {
      const [firstPage, ...laterPages] = cachedTickets?.pages ?? [];
      if (cachedTickets === undefined || firstPage === undefined) {
        return cachedTickets;
      }
      const isListed = cachedTickets.pages.some((page) =>
        page.tickets.some((listed) => listed.ticketId === ticket.ticketId),
      );
      if (isListed) {
        return cachedTickets;
      }
      return {
        ...cachedTickets,
        pages: [{ ...firstPage, tickets: [ticket, ...firstPage.tickets] }, ...laterPages],
      };
    },
  );
}
