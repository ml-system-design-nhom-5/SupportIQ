/**
 * The paths of the order screens (shop UI design, Screens): My orders at `/shop/orders` and Order
 * at `/shop/orders/{order_id}`.
 */
import { rootPathByArea } from "@/features/session";

/** The route of My orders, relative to the shop root. */
export const ORDERS_ROUTE = "orders";

/** The route of the Order screen, relative to the shop root. */
export const ORDER_ROUTE = `${ORDERS_ROUTE}/:orderId`;

/** The path of My orders. */
export const ORDERS_PATH = `${rootPathByArea.shop}/${ORDERS_ROUTE}`;

/**
 * Build the path of an order's page, optionally at one of its tickets. Order IDs are opaque
 * (CON-15), so they are encoded.
 *
 * @param orderId - The `order_id`.
 * @param fragment - The element to scroll to, for example the anchor of a ticket.
 * @returns For example `/shop/orders/ORD-20931#ticket-TCK-1042`.
 */
export function buildOrderPath(orderId: string, fragment?: string): string {
  const path = `${ORDERS_PATH}/${encodeURIComponent(orderId)}`;
  return fragment === undefined ? path : `${path}#${encodeURIComponent(fragment)}`;
}
