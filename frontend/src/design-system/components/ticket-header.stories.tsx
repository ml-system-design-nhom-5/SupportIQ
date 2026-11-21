import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { OrderChip } from "@/design-system/components/order-chip";
import { OrderRecord } from "@/design-system/components/order-record";
import {
  presentationByConsoleTicketStatus,
  presentationByHandlingMode,
} from "@/design-system/components/status-presentations";
import { TicketHeader } from "@/design-system/components/ticket-header";
import { TicketHeaderSkeleton } from "@/design-system/components/ticket-header-skeleton";

const meta = {
  title: "Design system/Components/TicketHeader",
  component: TicketHeader,
  parameters: { layout: "fullscreen" },
  args: {
    headingId: "ticket-heading",
    ticketId: "TCK-1042",
    status: presentationByConsoleTicketStatus.open,
    handlingMode: presentationByHandlingMode.assisted,
    order: (
      <OrderChip
        orderId="ORD-20931"
        summary="Delivered · Refund under review"
        otherOrderCount={0}
        isOpen={false}
        onOpenChange={fn()}
      >
        <OrderRecord orderId="ORD-20931" facts={[{ term: "Order", value: "Delivered" }]} />
      </OrderChip>
    ),
    customerName: "Linh Tran",
    receivedAt: "2026-11-05T08:42:00Z",
  },
} satisfies Meta<typeof TicketHeader>;

export default meta;

type Story = StoryObj<typeof meta>;

export const OpenAssisted: Story = {};
export const ClosedManualWithoutOrder: Story = {
  args: {
    status: presentationByConsoleTicketStatus.closed,
    handlingMode: presentationByHandlingMode.manual,
    order: <span className="text-sm text-text-muted">No order attached</span>,
  },
};
export const Loading: Story = { render: () => <TicketHeaderSkeleton /> };
