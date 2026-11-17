/**
 * The popover of a customer with several orders (console UI design, Order chip, order-multiple.png):
 * the orders on the left, the ticket's order first and tagged "This ticket", and the preview of
 * the selected order on the right. Each order is a toggle button, so the selected one is announced
 * as pressed.
 */
import type { ReactNode } from "react";

import { OrderRecordHeader } from "@/design-system/components/order-record-header";
import { Tag } from "@/design-system/components/tag";
import { formatCount } from "@/design-system/format/number";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** One order of the list. */
export type CustomerOrderOption = {
  readonly orderId: string;
  /** The order and refund statuses. */
  readonly summary: string;
  readonly isTicketOrder: boolean;
};

/** Props of {@link CustomerOrders}. */
export type CustomerOrdersProps = {
  readonly orders: readonly CustomerOrderOption[];
  readonly selectedOrderId: string;
  readonly onSelect: (orderId: string) => void;
  /** The preview of the selected order. */
  readonly preview: ReactNode;
};

/**
 * Render the list of orders and the preview.
 *
 * @param props - The orders, the selected one, the selection handler, and the preview.
 * @returns The content of the popover.
 */
export function CustomerOrders({
  orders,
  selectedOrderId,
  onSelect,
  preview,
}: CustomerOrdersProps) {
  return (
    <>
      <OrderRecordHeader title={`Orders of this customer (${formatCount(orders.length)})`} />
      <div className="grid grid-cols-5">
        <ul aria-label="Orders" className="col-span-2 flex flex-col border-r border-border">
          {orders.map((order) => {
            const isSelected = order.orderId === selectedOrderId;
            return (
              <li key={order.orderId} className="flex flex-col">
                <button
                  type="button"
                  aria-pressed={isSelected}
                  className={cn(
                    "flex flex-col items-start gap-1 border-b border-border px-4 py-3 text-left hover:bg-background focus-visible:-outline-offset-2",
                    FOCUS_RING_CLASSES,
                    isSelected && "bg-info-subtle",
                  )}
                  onClick={() => {
                    onSelect(order.orderId);
                  }}
                >
                  <span className="flex items-center gap-2">
                    <span className="font-mono">{order.orderId}</span>{" "}
                    {order.isTicketOrder ? <Tag tone="neutral">This ticket</Tag> : null}
                  </span>{" "}
                  <span className="text-xs text-text-muted">{order.summary}</span>
                </button>
              </li>
            );
          })}
        </ul>
        <div className="col-span-3 flex flex-col gap-3 p-4">{preview}</div>
      </div>
    </>
  );
}
