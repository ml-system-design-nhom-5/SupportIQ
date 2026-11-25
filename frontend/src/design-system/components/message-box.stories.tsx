import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { MessageBox } from "@/design-system/components/message-box";
import { StatusBanner } from "@/design-system/components/status-banner";

const meta = {
  title: "Design system/Shop/MessageBox",
  component: MessageBox,
  args: {
    inputId: "order-message",
    label: "Write to support about this order",
    text: { value: "", onChange: fn() },
    limit: { count: 0, max: 2000 },
    isSending: false,
    onSend: fn(),
  },
} satisfies Meta<typeof MessageBox>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Empty: Story = {};
export const Typed: Story = {
  args: {
    text: { value: "Can I also return the charging cable?", onChange: fn() },
    limit: { count: 37, max: 2000 },
  },
};
export const AtTheLimit: Story = {
  args: { text: { value: "x".repeat(2000), onChange: fn() }, limit: { count: 2000, max: 2000 } },
};
export const OverTheLimit: Story = {
  args: { text: { value: "x".repeat(2001), onChange: fn() }, limit: { count: 2001, max: 2000 } },
};
export const Sending: Story = {
  args: {
    text: { value: "Can I also return the charging cable?", onChange: fn() },
    limit: { count: 37, max: 2000 },
    isSending: true,
  },
};
export const SendFailed: Story = {
  args: {
    text: { value: "Can I also return the charging cable?", onChange: fn() },
    limit: { count: 37, max: 2000 },
    children: (
      <StatusBanner
        tone="danger"
        lead="Your message was not sent."
        traceId="1c80319c0af7651916cd43dd8448eb21"
      >
        The service is not available right now. Try again in a moment.
      </StatusBanner>
    ),
  },
};
