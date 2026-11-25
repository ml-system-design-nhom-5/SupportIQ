import type { Meta, StoryObj } from "@storybook/react-vite";

import { OrderRow } from "@/design-system/components/order-row";
import { RowList } from "@/design-system/components/row-list";
import {
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
} from "@/design-system/components/status-presentations";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const meta = {
  title: "Design system/Shop/OrderRow",
  component: OrderRow,
  decorators: [
    (Story) => (
      <RowList label="Your orders">
        <Story />
      </RowList>
    ),
  ],
  args: {
    orderId: "ORD-20990",
    placedAt: "2026-10-28T08:15:00Z",
    productSummary: "Desk lamp, Notebook set × 2",
    total: { amountMinor: 4250, currency: "USD" },
    href: "/shop/orders/ORD-20990",
    statuses: [
      { label: "Order", presentation: presentationByOrderStatus.shipped },
      { label: "Shipment", presentation: presentationByShipmentStatus.in_transit },
    ],
  },
} satisfies Meta<typeof OrderRow>;

export default meta;

type Story = StoryObj<typeof meta>;

export const InTransit: Story = {};
export const WithRefund: Story = {
  args: {
    orderId: "ORD-20931",
    productSummary: "Wireless headphones",
    statuses: [
      { label: "Order", presentation: presentationByOrderStatus.delivered },
      { label: "Shipment", presentation: presentationByShipmentStatus.delivered },
      { presentation: presentationByRefundStatus.under_review },
    ],
  },
};
export const UnknownStatus: Story = {
  args: {
    statuses: [
      { label: "Order", presentation: presentationByOrderStatus.unknown },
      { label: "Shipment", presentation: presentationByShipmentStatus.unknown },
    ],
  },
};
export const ManyProducts: Story = {
  args: {
    productSummary:
      "Desk lamp, Notebook set × 2, Running shoes, Wireless headphones, Travel mug × 3, Blender",
  },
};
export const LongUnbrokenOrderId: Story = {
  args: { orderId: "O".repeat(200) },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
