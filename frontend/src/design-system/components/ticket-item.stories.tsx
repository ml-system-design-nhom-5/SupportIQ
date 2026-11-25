import type { Meta, StoryObj } from "@storybook/react-vite";

import { presentationByShopTicketStatus } from "@/design-system/components/status-presentations";
import { TicketItem } from "@/design-system/components/ticket-item";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const meta = {
  title: "Design system/Shop/TicketItem",
  component: TicketItem,
  decorators: [
    (Story) => (
      <ul aria-label="Tickets about this order">
        <Story />
      </ul>
    ),
  ],
  args: {
    anchorId: "ticket-TCK-1042",
    ticketId: "TCK-1042",
    status: presentationByShopTicketStatus.received,
    message: "I asked for a refund for the headphones three weeks ago. When will it be paid?",
    createdAt: "2026-11-05T08:12:30Z",
  },
} satisfies Meta<typeof TicketItem>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Received: Story = {};
export const LongUnbrokenTicketId: Story = {
  args: { ticketId: "T".repeat(200) },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
export const Replied: Story = {
  args: {
    ticketId: "TCK-1017",
    status: presentationByShopTicketStatus.replied,
    message: "The left side of the headphones makes no sound. Can I return them?",
    createdAt: "2026-10-13T16:45:10Z",
    reply: {
      body: "Thank you for writing. Your refund request for the headphones is under review.",
      sentAt: "2026-10-14T09:25:00Z",
    },
  },
};
export const LongNonAsciiMessage: Story = {
  args: { message: `${"Tôi chưa nhận được tiền hoàn cho đơn hàng này. ".repeat(40)}🙏` },
};
