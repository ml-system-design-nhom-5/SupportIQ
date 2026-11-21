import type { Meta, StoryObj } from "@storybook/react-vite";

import { DateText } from "@/design-system/components/date-text";
import { OrderSummary } from "@/design-system/components/order-summary";
import {
  presentationByOrderStatus,
  presentationByRefundStatus,
  presentationByShipmentStatus,
} from "@/design-system/components/status-presentations";

const meta = {
  title: "Design system/Shop/OrderSummary",
  component: OrderSummary,
  args: {
    statuses: [
      {
        label: "Order",
        presentation: presentationByOrderStatus.delivered,
        detail: (
          <>
            Placed <DateText timestamp="2026-10-02T19:30:00Z" />
          </>
        ),
      },
      {
        label: "Shipment",
        presentation: presentationByShipmentStatus.delivered,
        detail: <DateText timestamp="2026-10-06T12:05:00Z" />,
      },
      {
        label: "Refund",
        presentation: presentationByRefundStatus.under_review,
        detail: (
          <>
            Requested <DateText timestamp="2026-10-14T09:20:00Z" />
          </>
        ),
      },
    ],
    lines: [
      {
        key: "PRD-1002",
        productName: "Wireless headphones",
        quantity: 1,
        href: "/shop/products/PRD-1002",
      },
    ],
    total: { amountMinor: 8900, currency: "USD" },
  },
} satisfies Meta<typeof OrderSummary>;

export default meta;

type Story = StoryObj<typeof meta>;

export const RefundUnderReview: Story = {};
export const WithoutRefundAndTwoLines: Story = {
  args: {
    statuses: [
      { label: "Order", presentation: presentationByOrderStatus.shipped },
      { label: "Shipment", presentation: presentationByShipmentStatus.in_transit },
      { label: "Refund", presentation: presentationByRefundStatus.none, detail: "Not requested" },
    ],
    lines: [
      { key: "PRD-1001", productName: "Desk lamp", quantity: 1, href: "/shop/products/PRD-1001" },
      {
        key: "PRD-1003",
        productName: "Notebook set",
        quantity: 2,
        href: "/shop/products/PRD-1003",
      },
    ],
    total: { amountMinor: 4250, currency: "USD" },
  },
};
