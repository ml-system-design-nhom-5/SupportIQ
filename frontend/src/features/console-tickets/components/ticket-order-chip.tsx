/**
 * The order chip of a ticket (console UI design, Order chip). With one order, the popover holds
 * its facts. With other orders, it lists the customer's orders, the ticket's order first and
 * selected each time the popover opens, from the chip or from an order citation marker, and
 * previews the selected one. The preview of another order has no shipping address and says that
 * the AI did not use it, because `ai-service` receives only the ticket's order context.
 */
import { Info } from "lucide-react";
import { useState } from "react";

import {
  CustomerOrders,
  type DialogReturnFocus,
  InlineMessage,
  OrderChip,
  OrderFacts,
  OrderRecord,
  Stack,
} from "@/design-system";
import {
  buildOrderFacts,
  buildTicketOrderFacts,
  type Order,
  summarizeOrder,
  type TicketOrder,
} from "@/features/console-tickets/model/order";

/** The order popover: whether it is open, and where the focus returns when a marker opened it. */
export type OrderPopoverState = {
  readonly isOpen: boolean;
  readonly returnFocus?: DialogReturnFocus;
};

/** Props of {@link TicketOrderChip}. */
type TicketOrderChipProps = {
  readonly order: TicketOrder;
  /** The customer's other orders; empty when there are none. */
  readonly otherOrders: readonly Order[];
  readonly popover: OrderPopoverState;
  readonly onOpenChange: (isOpen: boolean) => void;
};

/** Props of {@link CustomerOrdersPreview}. */
type CustomerOrdersPreviewProps = Pick<TicketOrderChipProps, "order" | "otherOrders">;

/**
 * Render the order chip and its popover.
 *
 * @param props - The ticket's order, the other orders, and the state of the popover.
 * @returns The chip.
 */
export function TicketOrderChip({
  order,
  otherOrders,
  popover,
  onOpenChange,
}: TicketOrderChipProps) {
  return (
    <OrderChip
      orderId={order.orderId}
      summary={summarizeOrder(order)}
      otherOrderCount={otherOrders.length}
      isOpen={popover.isOpen}
      onOpenChange={onOpenChange}
      {...(popover.returnFocus === undefined ? {} : { returnFocus: popover.returnFocus })}
    >
      {otherOrders.length > 0 ? (
        <CustomerOrdersPreview order={order} otherOrders={otherOrders} />
      ) : (
        <OrderRecord orderId={order.orderId} facts={buildTicketOrderFacts(order)} />
      )}
    </OrderChip>
  );
}

/**
 * Render the customer's orders and the preview of the selected one. The popover mounts it each
 * time it opens, so the ticket's order is selected again on every opening.
 *
 * @param props - The ticket's order and the other orders.
 * @returns The list with the preview.
 */
function CustomerOrdersPreview({ order, otherOrders }: CustomerOrdersPreviewProps) {
  const [selectedOrderId, setSelectedOrderId] = useState(order.orderId);
  const selectedOtherOrder = otherOrders.find((other) => other.orderId === selectedOrderId);
  return (
    <CustomerOrders
      orders={[order, ...otherOrders].map((listed) => ({
        orderId: listed.orderId,
        summary: summarizeOrder(listed),
        isTicketOrder: listed.orderId === order.orderId,
      }))}
      selectedOrderId={selectedOtherOrder?.orderId ?? order.orderId}
      onSelect={setSelectedOrderId}
      preview={
        selectedOtherOrder === undefined ? (
          <OrderFacts facts={buildTicketOrderFacts(order)} />
        ) : (
          <Stack gap="3">
            <InlineMessage tone="muted" icon={Info}>
              Not the order of this ticket. The AI did not use it.
            </InlineMessage>
            <OrderFacts facts={buildOrderFacts(selectedOtherOrder)} />
          </Stack>
        )
      }
    />
  );
}
