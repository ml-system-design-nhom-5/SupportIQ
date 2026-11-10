/**
 * The query keys of the orders feature (TS-19).
 */

/** The one key factory of the orders feature. */
export const orderQueryKeys = {
  all: ["shop-orders"] as const,
  orders: () => [...orderQueryKeys.all, "orders"] as const,
  order: (orderId: string) => [...orderQueryKeys.all, "order", orderId] as const,
};
