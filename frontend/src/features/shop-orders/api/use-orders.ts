/**
 * Read the customer's orders page by page (`listShopOrders`, CON-14), newest first.
 */
import {
  type InfiniteData,
  useInfiniteQuery,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { orderQueryKeys } from "@/features/shop-orders/api/order-query-keys";
import { type OrderPage, toOrderPage } from "@/features/shop-orders/model/order";

/**
 * Read the pages of My orders.
 *
 * @returns The infinite query; `fetchNextPage` follows `next_cursor` while there is one.
 */
export function useOrders(): UseInfiniteQueryResult<InfiniteData<OrderPage, string | undefined>> {
  const client = useBackendClient();
  return useInfiniteQuery({
    queryKey: orderQueryKeys.orders(),
    initialPageParam: undefined,
    queryFn: ({ pageParam, signal }: { pageParam: string | undefined; signal: AbortSignal }) =>
      requestData(
        () =>
          client.GET("/v1/shop/orders", {
            params: { query: pageParam === undefined ? {} : { cursor: pageParam } },
            signal,
          }),
        toOrderPage,
      ),
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });
}
