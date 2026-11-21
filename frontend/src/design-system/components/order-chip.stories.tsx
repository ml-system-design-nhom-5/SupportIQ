import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { expect, fn, screen, userEvent, within } from "storybook/test";

import { CustomerOrders } from "@/design-system/components/customer-orders";
import { OrderChip } from "@/design-system/components/order-chip";
import { OrderFacts } from "@/design-system/components/order-facts";
import { OrderRecord } from "@/design-system/components/order-record";

const ticketOrderFacts = [
  { term: "Order", value: "Delivered", detail: "Placed 2 Oct 2026" },
  { term: "Shipment", value: "Delivered", detail: "Delivered 6 Oct 2026" },
  { term: "Refund", value: "Refund under review", detail: "Requested 14 Oct 2026" },
  { term: "Total", value: "$89.00", detail: "1 item" },
  { term: "Items", value: "Wireless headphones × 1" },
  { term: "Ship to", value: "12 Sample Street, Sample City" },
];

const meta = {
  title: "Design system/Components/OrderChip",
  component: OrderChip,
  args: {
    orderId: "ORD-20931",
    summary: "Delivered · Refund under review",
    otherOrderCount: 0,
    isOpen: false,
    onOpenChange: fn(),
    children: <OrderRecord orderId="ORD-20931" facts={ticketOrderFacts} />,
  },
} satisfies Meta<typeof OrderChip>;

export default meta;

type Story = StoryObj<typeof meta>;

export const OneOrder: Story = {};
export const OneOrderOpen: Story = {
  args: { isOpen: true },
  play: async () => {
    const popover = await screen.findByRole("dialog", { name: "Order ORD-20931" });

    await expect(within(popover).getByText("From order records, not AI")).toBeVisible();
  },
};
export const SeveralOrdersOpen: Story = {
  args: { otherOrderCount: 2, isOpen: true },
  render: (args) => <SeveralOrders {...args} />,
  play: async () => {
    const popover = await screen.findByRole("dialog", { name: "Orders of this customer" });
    await userEvent.click(within(popover).getByRole("button", { name: /ORD-20874/ }));

    await expect(
      within(popover).getByText("Not the order of this ticket. The AI did not use it."),
    ).toBeVisible();
  },
};

/**
 * Render the chip of a customer with three orders, the selection held in the story.
 *
 * @param props - The props of the chip.
 * @returns The chip with its open popover.
 */
function SeveralOrders(props: Parameters<typeof OrderChip>[0]) {
  const [selectedOrderId, setSelectedOrderId] = useState("ORD-20931");
  const isTicketOrder = selectedOrderId === "ORD-20931";
  return (
    <OrderChip {...props}>
      <CustomerOrders
        orders={[
          {
            orderId: "ORD-20931",
            summary: "Delivered · Refund under review",
            isTicketOrder: true,
          },
          {
            orderId: "ORD-20874",
            summary: "Shipped · In transit",
            isTicketOrder: false,
          },
          {
            orderId: "ORD-20655",
            summary: "Delivered",
            isTicketOrder: false,
          },
        ]}
        selectedOrderId={selectedOrderId}
        onSelect={setSelectedOrderId}
        preview={
          <>
            {isTicketOrder ? null : (
              <p className="text-sm text-text-muted">
                Not the order of this ticket. The AI did not use it.
              </p>
            )}
            <OrderFacts
              facts={
                isTicketOrder
                  ? ticketOrderFacts
                  : [{ term: "Order", value: "Shipped", detail: "Placed 20 Oct 2026" }]
              }
            />
          </>
        }
      />
    </OrderChip>
  );
}
