/**
 * Read the customer's tickets page by page (`listShopTickets`, CON-14), newest first: every ticket
 * for Support, or the tickets of one order for its order page.
 */
import {
  type InfiniteData,
  type QueryKey,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";

import { type BackendClient, useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { supportQueryKeys } from "@/features/shop-support/api/support-query-keys";
import { type ShopTicketPage, toShopTicketPage } from "@/features/shop-support/model/ticket";

/** The infinite query of a ticket list. */
export type TicketListQuery = UseInfiniteQueryResult<
  InfiniteData<ShopTicketPage, string | undefined>
>;

/** What one page request needs. */
type TicketPageRequest = {
  readonly client: BackendClient;
  readonly orderId: string | undefined;
  readonly cursor: string | undefined;
  readonly signal: AbortSignal;
};

/** The options that differ between the two ticket lists. */
type TicketListOptions = {
  readonly queryKey: QueryKey;
  readonly orderId: string | undefined;
  readonly shouldRefetchOnWindowFocus: boolean;
};

/**
 * Read the tickets of one order. Like its order, the list loads again when the window regains
 * focus, so a reply appears without polling (shop UI design, Alternatives considered).
 *
 * @param orderId - The order.
 * @returns The infinite query of the order's tickets.
 */
export function useOrderTickets(orderId: string): TicketListQuery {
  return useTicketList({
    queryKey: supportQueryKeys.ticketsOfOrder(orderId),
    orderId,
    shouldRefetchOnWindowFocus: true,
  });
}

/**
 * Read every ticket of the customer, for Support.
 *
 * @returns The infinite query of all tickets.
 */
export function useAllTickets(): TicketListQuery {
  return useTicketList({
    queryKey: supportQueryKeys.allTickets(),
    orderId: undefined,
    shouldRefetchOnWindowFocus: false,
  });
}

/**
 * Fetch one page of tickets. Neither an empty cursor nor an empty order ID is ever sent, because
 * `backend` refuses both (contracts/README.md, The mock).
 *
 * @param request - The client, the order filter, the cursor, and the abort signal.
 * @returns The page.
 */
function fetchTicketPage(request: TicketPageRequest): Promise<ShopTicketPage> {
  const query = {
    ...(request.orderId === undefined ? {} : { order_id: request.orderId }),
    ...(request.cursor === undefined ? {} : { cursor: request.cursor }),
  };
  return requestData(
    () => request.client.GET("/v1/shop/tickets", { params: { query }, signal: request.signal }),
    toShopTicketPage,
  );
}

/**
 * Read a ticket list.
 *
 * @param options - The key, the order filter, and whether the list reloads on window focus.
 * @returns The infinite query.
 */
function useTicketList(options: TicketListOptions): TicketListQuery {
  const client = useBackendClient();
  return useInfiniteQuery({
    queryKey: options.queryKey,
    initialPageParam: undefined,
    queryFn: ({ pageParam, signal }: { pageParam: string | undefined; signal: AbortSignal }) =>
      fetchTicketPage({ client, orderId: options.orderId, cursor: pageParam, signal }),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
    refetchOnWindowFocus: options.shouldRefetchOnWindowFocus,
  });
}
