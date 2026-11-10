/**
 * Turn an order into the props of the design-system order blocks: which status presentation each
 * status has (UI-12), and which date goes under it (shop UI design, Order).
 */
import {
  DateText,
  type OrderRowStatus,
  type OrderSummaryStatus,
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
} from "@/design-system";
import type { Order, Shipment } from "@/features/shop-orders/model/order";

/**
 * Build the statuses of an order row in My orders: order, shipment, and the refund if there is one.
 *
 * @param order - The order.
 * @returns The statuses with their labels.
 */
export function buildOrderRowStatuses(order: Order): readonly OrderRowStatus[] {
  const statuses: OrderRowStatus[] = [
    { label: "Order", presentation: presentationByOrderStatus[order.status] },
    { label: "Shipment", presentation: presentationByShipmentStatus[order.shipment.status] },
  ];
  if (order.refund !== undefined) {
    statuses.push({ presentation: presentationByRefundStatus[order.refund.status] });
  }
  return statuses;
}

/**
 * Build the status cells of the order card: order, shipment, and refund with their dates. An
 * order without a refund shows "No refund" and "Not requested".
 *
 * @param order - The order.
 * @returns The three status cells.
 */
export function buildOrderSummaryStatuses(order: Order): readonly OrderSummaryStatus[] {
  const shipmentDate = describeShipmentDate(order.shipment);
  return [
    {
      label: "Order",
      presentation: presentationByOrderStatus[order.status],
      detail: (
        <>
          Placed <DateText timestamp={order.placedAt} />
        </>
      ),
    },
    {
      label: "Shipment",
      presentation: presentationByShipmentStatus[order.shipment.status],
      ...(shipmentDate === undefined ? {} : { detail: shipmentDate }),
    },
    order.refund === undefined
      ? { label: "Refund", presentation: presentationByRefundStatus.none, detail: "Not requested" }
      : {
          label: "Refund",
          presentation: presentationByRefundStatus[order.refund.status],
          detail: (
            <>
              Requested <DateText timestamp={order.refund.requestedAt} />
            </>
          ),
        },
  ];
}

/**
 * Choose the date under the shipment status: the delivery date, otherwise the estimate.
 *
 * @param shipment - The shipment.
 * @returns The date line, or undefined when `backend` sent no date.
 */
function describeShipmentDate(shipment: Shipment) {
  if (shipment.deliveredAt !== undefined) {
    return <DateText timestamp={shipment.deliveredAt} />;
  }
  if (shipment.estimatedDeliveryAt !== undefined) {
    return (
      <>
        Expected <DateText timestamp={shipment.estimatedDeliveryAt} />
      </>
    );
  }
  return undefined;
}
