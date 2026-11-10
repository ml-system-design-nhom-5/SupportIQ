/**
 * The query keys of the shop support feature (TS-19).
 */

/** The one key factory of the shop support feature. */
export const supportQueryKeys = {
  all: ["shop-support"] as const,
  /** Every ticket list: invalidating it reloads the lists of every order and of Support. */
  ticketLists: () => [...supportQueryKeys.all, "tickets"] as const,
  allTickets: () => [...supportQueryKeys.ticketLists(), { orderId: null }] as const,
  ticketsOfOrder: (orderId: string) => [...supportQueryKeys.ticketLists(), { orderId }] as const,
};
