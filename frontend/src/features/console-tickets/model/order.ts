/**
 * The order of a ticket and the customer's other orders (console UI design, Order chip), mapped
 * from `ConsoleOrderView` and `ConsoleOtherOrderView` (TS-09), and the facts that the order
 * popover lists. Order data comes from the order records, not from the AI. All of it is
 * Confidential: shown, never logged.
 */
import type { Money, OrderStatusName, RefundStatusName, ShipmentStatusName } from "@/design-system";
import {
  formatCount,
  formatDate,
  formatMoney,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
} from "@/design-system";
import {
  requireMembers,
  toMoney,
  toOrderStatus,
  toRefundStatus,
  toShipmentStatus,
} from "@/features/backend-requests";
import type {
  ConsoleOrderContract,
  ConsoleOtherOrderContract,
  OrderLineContract,
} from "@/features/console-tickets/api/contract-types";

/** One line of an order. */
export type OrderLine = {
  readonly productName: string;
  readonly quantity: number;
};

/** An order: the ticket's own order, or another order of the same customer. */
export type Order = {
  readonly orderId: string;
  readonly status: OrderStatusName;
  readonly placedAt: string;
  readonly total: Money;
  readonly lines: readonly OrderLine[];
  /** Absent when the order has no shipment. */
  readonly shipmentStatus?: ShipmentStatusName;
  /** Absent when no refund was requested. */
  readonly refundStatus?: Exclude<RefundStatusName, "none">;
  /** When the carrier expects to deliver; only the ticket's order carries it. */
  readonly estimatedDeliveryAt?: string;
  /** When the carrier delivered; only the ticket's order carries it. */
  readonly deliveredAt?: string;
  /** When the refund was requested; only the ticket's order carries it. */
  readonly refundRequestedAt?: string;
};

/** The order of the ticket, with the details that only this order shows (SEC-17). */
export type TicketOrder = Order & {
  readonly shippingCost: Money;
  readonly shippingAddress: string;
};

/** One fact of the order popover, such as "Order: Delivered · Placed 2 Oct 2026". */
export type OrderFact = {
  readonly term: string;
  readonly value: string;
  readonly detail?: string;
};

/**
 * Map the order of a ticket.
 *
 * @param order - A `ConsoleOrderView`.
 * @returns The view model.
 */
export function toTicketOrder(order: ConsoleOrderContract): TicketOrder {
  requireMembers(order, ["shipping_cost", "shipping_address"]);
  const shipment = order.shipment;
  const refund = order.refund;
  return {
    ...toOrder({
      ...order,
      ...(shipment === undefined ? {} : { shipment_status: shipment.shipment_status }),
      ...(refund === undefined ? {} : { refund_status: refund.refund_status }),
    }),
    shippingCost: toMoney(order.shipping_cost),
    shippingAddress: order.shipping_address,
    ...(shipment?.estimated_delivery_at === undefined
      ? {}
      : { estimatedDeliveryAt: shipment.estimated_delivery_at }),
    ...(shipment?.delivered_at === undefined ? {} : { deliveredAt: shipment.delivered_at }),
    ...(refund === undefined ? {} : { refundRequestedAt: refund.refund_requested_at }),
  };
}

/**
 * Map another order of the customer. It has no shipping address (SEC-17).
 *
 * @param order - A `ConsoleOtherOrderView`.
 * @returns The view model.
 */
export function toOrder(order: ConsoleOtherOrderContract): Order {
  requireMembers(order, ["order_id", "order_status", "placed_at", "order_total", "lines"]);
  return {
    orderId: order.order_id,
    status: toOrderStatus(order.order_status),
    placedAt: order.placed_at,
    total: toMoney(order.order_total),
    lines: order.lines.map(toOrderLine),
    ...(order.shipment_status === undefined
      ? {}
      : { shipmentStatus: toShipmentStatus(order.shipment_status) }),
    ...(order.refund_status === undefined
      ? {}
      : { refundStatus: toRefundStatus(order.refund_status) }),
  };
}

/**
 * Summarize an order on the chip and in the order list: its status and its refund status, which
 * stay visible without a click (console UI design, placement rule 8).
 *
 * @param order - An order.
 * @returns For example "Delivered · Refund under review".
 */
export function summarizeOrder(order: Order): string {
  return `${presentationByOrderStatus[order.status].label} · ${getRefundLabel(order)}`;
}

/**
 * List the facts of an order for the preview of another order of the customer.
 *
 * @param order - An order.
 * @returns The status, the shipment, the refund, the total, and the items.
 */
export function buildOrderFacts(order: Order): readonly OrderFact[] {
  return [
    {
      term: "Order",
      value: presentationByOrderStatus[order.status].label,
      detail: `Placed ${formatDate(order.placedAt)}`,
    },
    buildShipmentFact(order),
    buildRefundFact(order),
    { term: "Total", value: formatMoney(order.total), detail: describeItemCount(order.lines) },
    { term: "Items", value: describeLines(order.lines) },
  ];
}

/**
 * List the facts of the ticket's order for its popover.
 *
 * @param order - The ticket's order.
 * @returns The facts of {@link buildOrderFacts}, the shipping cost, and the shipping address.
 */
export function buildTicketOrderFacts(order: TicketOrder): readonly OrderFact[] {
  return [
    ...buildOrderFacts(order),
    { term: "Shipping", value: formatMoney(order.shippingCost) },
    { term: "Ship to", value: order.shippingAddress },
  ];
}

/**
 * Map a line of an order.
 *
 * @param line - A `ShopOrderLine`.
 * @returns The product name and the quantity.
 */
function toOrderLine(line: OrderLineContract): OrderLine {
  requireMembers(line, ["product_name", "quantity"]);
  return { productName: line.product_name, quantity: line.quantity };
}

/**
 * Name the refund of an order.
 *
 * @param order - An order.
 * @returns The label of its refund status, or "No refund".
 */
function getRefundLabel(order: Order): string {
  return presentationByRefundStatus[order.refundStatus ?? "none"].label;
}

/**
 * Build the shipment fact, with the delivery date or the expected date when the order has one.
 *
 * @param order - An order.
 * @returns The fact.
 */
function buildShipmentFact(order: Order): OrderFact {
  if (order.shipmentStatus === undefined) {
    return { term: "Shipment", value: "No shipment" };
  }
  const value = presentationByShipmentStatus[order.shipmentStatus].label;
  if (order.deliveredAt !== undefined) {
    return { term: "Shipment", value, detail: `Delivered ${formatDate(order.deliveredAt)}` };
  }
  if (order.estimatedDeliveryAt !== undefined) {
    return { term: "Shipment", value, detail: `Due ${formatDate(order.estimatedDeliveryAt)}` };
  }
  return { term: "Shipment", value };
}

/**
 * Build the refund fact, with the date of the request when the order has one.
 *
 * @param order - An order.
 * @returns The fact.
 */
function buildRefundFact(order: Order): OrderFact {
  const value = getRefundLabel(order);
  if (order.refundRequestedAt !== undefined) {
    return { term: "Refund", value, detail: `Requested ${formatDate(order.refundRequestedAt)}` };
  }
  return { term: "Refund", value };
}

/**
 * Count the items of an order.
 *
 * @param lines - The lines of the order.
 * @returns For example "1 item" or "3 items".
 */
function describeItemCount(lines: readonly OrderLine[]): string {
  const itemCount = lines.reduce((count, line) => count + line.quantity, 0);
  return `${formatCount(itemCount)} ${itemCount === 1 ? "item" : "items"}`;
}

/**
 * Name the lines of an order.
 *
 * @param lines - The lines of the order.
 * @returns For example "Wireless headphones × 1, Desk lamp × 2".
 */
function describeLines(lines: readonly OrderLine[]): string {
  return lines.map((line) => `${line.productName} × ${formatCount(line.quantity)}`).join(", ");
}
