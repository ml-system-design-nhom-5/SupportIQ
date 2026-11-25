/**
 * Mappings of the order, shipment, and refund statuses, which the shop and the console both read
 * (`OrderStatus`, `ShipmentStatus`, and `RefundStatus`, CON-09). Each status from `backend` is
 * mapped once, here; a value that this version does not know becomes `unknown`, which has a
 * neutral presentation (CON-22, TS-15).
 */
import type { OrderStatusName, RefundStatusName, ShipmentStatusName } from "@/design-system";

const orderStatuses: ReadonlySet<string> = new Set([
  "placed",
  "processing",
  "shipped",
  "delivered",
  "cancelled",
]);

const shipmentStatuses: ReadonlySet<string> = new Set([
  "not_shipped",
  "in_transit",
  "delivered",
  "delayed",
  "lost",
]);

const refundStatuses: ReadonlySet<string> = new Set([
  "requested",
  "under_review",
  "approved",
  "rejected",
  "paid",
]);

/**
 * Map an order status.
 *
 * @param value - The `order_status` from `backend`.
 * @returns The status, or `unknown` for a value this version does not know (CON-22).
 */
export function toOrderStatus(value: string): OrderStatusName {
  return isOrderStatus(value) ? value : "unknown";
}

/**
 * Map a shipment status.
 *
 * @param value - The `shipment_status` from `backend`.
 * @returns The status, or `unknown` for a value this version does not know (CON-22).
 */
export function toShipmentStatus(value: string): ShipmentStatusName {
  return isShipmentStatus(value) ? value : "unknown";
}

/**
 * Map a refund status.
 *
 * @param value - The `refund_status` from `backend`.
 * @returns The status, or `unknown` for a value this version does not know (CON-22).
 */
export function toRefundStatus(value: string): Exclude<RefundStatusName, "none"> {
  return isRefundStatus(value) ? value : "unknown";
}

/**
 * Tell whether a value is a known order status.
 *
 * @param value - The `order_status` from `backend`.
 * @returns True for a value of the contract's `OrderStatus`.
 */
function isOrderStatus(value: string): value is Exclude<OrderStatusName, "unknown"> {
  return orderStatuses.has(value);
}

/**
 * Tell whether a value is a known shipment status.
 *
 * @param value - The `shipment_status` from `backend`.
 * @returns True for a value of the contract's `ShipmentStatus`.
 */
function isShipmentStatus(value: string): value is Exclude<ShipmentStatusName, "unknown"> {
  return shipmentStatuses.has(value);
}

/**
 * Tell whether a value is a known refund status.
 *
 * @param value - The `refund_status` from `backend`.
 * @returns True for a value of the contract's `RefundStatus`.
 */
function isRefundStatus(value: string): value is Exclude<RefundStatusName, "unknown" | "none"> {
  return refundStatuses.has(value);
}
