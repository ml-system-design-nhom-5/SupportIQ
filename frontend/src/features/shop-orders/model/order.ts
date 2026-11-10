/**
 * The view models of the customer's orders and their mappings from the contract (TS-09). Every
 * status from `backend` is mapped once, here; a value that this version does not know becomes
 * `unknown`, which has a neutral presentation (CON-22, TS-15).
 */
import type { Money, OrderStatusName, RefundStatusName, ShipmentStatusName } from "@/design-system";
import { formatCount } from "@/design-system";
import { requireMembers, toMoney } from "@/features/backend-requests";
import type {
  ShopOrderContract,
  ShopOrderPageContract,
} from "@/features/shop-orders/api/contract-types";

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

/** One line of an order. */
export type OrderLine = {
  readonly productId: string;
  readonly productName: string;
  readonly quantity: number;
};

/** The shipment of an order. */
export type Shipment = {
  readonly status: ShipmentStatusName;
  /** When the carrier expects to deliver; absent when there is no estimate. */
  readonly estimatedDeliveryAt?: string;
  /** When the carrier delivered; present when the parcel was delivered. */
  readonly deliveredAt?: string;
};

/** The refund of an order. */
export type Refund = {
  readonly status: Exclude<RefundStatusName, "none">;
  readonly requestedAt: string;
};

/** One of the customer's orders. All of it is Confidential and is never logged. */
export type Order = {
  readonly orderId: string;
  readonly status: OrderStatusName;
  readonly placedAt: string;
  readonly total: Money;
  readonly lines: readonly OrderLine[];
  readonly shipment: Shipment;
  /** Absent when no refund was requested for the order. */
  readonly refund?: Refund;
};

/** One page of the customer's orders (CON-14). */
export type OrderPage = {
  readonly orders: readonly Order[];
  readonly nextCursor?: string;
};

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
 * Map a contract order.
 *
 * @param order - A `ShopOrderView`.
 * @returns The view model.
 */
export function toOrder(order: ShopOrderContract): Order {
  requireMembers(order, [
    "order_id",
    "order_status",
    "placed_at",
    "order_total",
    "lines",
    "shipment",
  ]);
  const mapped: Order = {
    orderId: order.order_id,
    status: toOrderStatus(order.order_status),
    placedAt: order.placed_at,
    total: toMoney(order.order_total),
    lines: order.lines.map(toOrderLine),
    shipment: toShipment(order.shipment),
  };
  if (order.refund === undefined) {
    return mapped;
  }
  requireMembers(order.refund, ["refund_status", "refund_requested_at"]);
  return {
    ...mapped,
    refund: {
      status: toRefundStatus(order.refund.refund_status),
      requestedAt: order.refund.refund_requested_at,
    },
  };
}

/**
 * Map a page of `listShopOrders`.
 *
 * @param page - A `ShopOrderPage`.
 * @returns The orders and the cursor of the next page.
 */
export function toOrderPage(page: ShopOrderPageContract): OrderPage {
  const orders = page.items.map(toOrder);
  return page.next_cursor === undefined ? { orders } : { orders, nextCursor: page.next_cursor };
}

/**
 * Name the products of an order in one line, as My orders shows them.
 *
 * @param lines - The lines of the order.
 * @returns For example "Desk lamp, Notebook set × 2".
 */
export function summarizeOrderLines(lines: readonly OrderLine[]): string {
  return lines
    .map((line) =>
      line.quantity > 1 ? `${line.productName} × ${formatCount(line.quantity)}` : line.productName,
    )
    .join(", ");
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

/**
 * Map the shipment of an order.
 *
 * @param shipment - The `shipment` of a `ShopOrderView`.
 * @returns The view model, with only the dates that `backend` sent.
 */
function toShipment(shipment: ShopOrderContract["shipment"]): Shipment {
  requireMembers(shipment, ["shipment_status"]);
  return {
    status: toShipmentStatus(shipment.shipment_status),
    ...(shipment.estimated_delivery_at === undefined
      ? {}
      : { estimatedDeliveryAt: shipment.estimated_delivery_at }),
    ...(shipment.delivered_at === undefined ? {} : { deliveredAt: shipment.delivered_at }),
  };
}

/**
 * Map a line of a contract order.
 *
 * @param line - An item of `lines` of a `ShopOrderView`.
 * @returns The view model.
 */
function toOrderLine(line: ShopOrderContract["lines"][number]): OrderLine {
  requireMembers(line, ["product_id", "product_name", "quantity"]);
  return {
    productId: line.product_id,
    productName: line.product_name,
    quantity: line.quantity,
  };
}
