/**
 * Read one of the customer's orders (`getShopOrder`). The order page loads it again in the
 * background when the window regains focus, and does not poll (shop UI design, Alternatives
 * considered).
 */
import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { useBackendClient } from "@/api/client";
import { requestData } from "@/features/backend-requests";
import { orderQueryKeys } from "@/features/shop-orders/api/order-query-keys";
import { type Order, toOrder } from "@/features/shop-orders/model/order";

/**
 * Read an order.
 *
 * @param orderId - The `order_id` from the address.
 * @returns The query of the order; a `404` means that it does not exist or is another
 *   customer's (SEC-17).
 */
export function useOrder(orderId: string): UseQueryResult<Order> {
  const client = useBackendClient();
  return useQuery({
    queryKey: orderQueryKeys.order(orderId),
    queryFn: ({ signal }) =>
      requestData(
        () =>
          client.GET("/v1/shop/orders/{order_id}", {
            params: { path: { order_id: orderId } },
            signal,
          }),
        toOrder,
      ),
    refetchOnWindowFocus: true,
  });
}
