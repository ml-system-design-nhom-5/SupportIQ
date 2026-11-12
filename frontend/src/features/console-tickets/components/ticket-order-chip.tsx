/**
 * The order chip of a ticket (console UI design, Order chip). With one order, the popover holds
 * its facts. With other orders, it lists the customer's orders, the ticket's order first and
 * selected when it opens, and previews the selected one. The preview of another order has no
 * shipping address and says that the AI did not use it, because `ai-service` receives only the
 * ticket's order context.
 */
import { Info } from "lucide-react";
import { useState } from "react";

import {
  CustomerOrders,
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

/** Props of {@link TicketOrderChip}. */
type TicketOrderChipProps = {
  readonly order: TicketOrder;
  /** The customer's other orders; empty when there are none. */
  readonly otherOrders: readonly Order[];
  readonly isOpen: boolean;
  readonly onOpenChange: (isOpen: boolean) => void;
};

/**
 * Render the order chip and its popover.
 *
 * @param props - The ticket's order, the other orders, and the open state of the popover.
 * @returns The chip.
 */
export function TicketOrderChip({
  order,
  otherOrders,
  isOpen,
  onOpenChange,
}: TicketOrderChipProps) {
  const [selectedOrderId, setSelectedOrderId] = useState(order.orderId);
  const hasOtherOrders = otherOrders.length > 0;
  const handleOpenChange = (isNowOpen: boolean) => {
    if (isNowOpen) {
      setSelectedOrderId(order.orderId);
    }
    onOpenChange(isNowOpen);
  };
  const selectedOtherOrder = otherOrders.find((other) => other.orderId === selectedOrderId);
  const preview =
    selectedOtherOrder === undefined ? (
      <OrderFacts facts={buildTicketOrderFacts(order)} />
    ) : (
      <Stack gap="3">
        <InlineMessage tone="muted" icon={Info}>
          Not the order of this ticket. The AI did not use it.
        </InlineMessage>
        <OrderFacts facts={buildOrderFacts(selectedOtherOrder)} />
      </Stack>
    );
  return (
    <OrderChip
      orderId={order.orderId}
      summary={summarizeOrder(order)}
      otherOrderCount={otherOrders.length}
      popoverLabel={hasOtherOrders ? "Orders of this customer" : `Order ${order.orderId}`}
      isOpen={isOpen}
      onOpenChange={handleOpenChange}
    >
      {hasOtherOrders ? (
        <CustomerOrders
          orders={[order, ...otherOrders].map((listed) => ({
            orderId: listed.orderId,
            summary: summarizeOrder(listed),
            isTicketOrder: listed.orderId === order.orderId,
          }))}
          selectedOrderId={selectedOtherOrder?.orderId ?? order.orderId}
          onSelect={setSelectedOrderId}
          preview={preview}
        />
      ) : (
        <OrderRecord orderId={order.orderId} facts={buildTicketOrderFacts(order)} />
      )}
    </OrderChip>
  );
}
