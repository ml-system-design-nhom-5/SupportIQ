import type { Meta, StoryObj } from "@storybook/react-vite";

import { MessageBubble } from "@/design-system/components/message-bubble";
import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Components/MessageBubble",
  component: MessageBubble,
  args: {
    author: "customer",
    header: (
      <>
        <Text>You</Text> · 3 weeks ago
      </>
    ),
    text: "Hi, I sent back the headphones from order ORD-20931 almost two weeks ago.",
  },
} satisfies Meta<typeof MessageBubble>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FromCustomer: Story = {};
export const FromSupport: Story = {
  args: {
    author: "support",
    header: (
      <>
        <Text>Reply from support</Text> · 3 weeks ago
      </>
    ),
    text: "Thank you for your patience. Your refund request is under review.",
  },
};
export const LongTextWithLineBreaks: Story = {
  args: { text: `${"A long message. ".repeat(60)}\n\nSecond paragraph.` },
};
export const NonAsciiText: Story = {
  args: { text: "Tôi chưa nhận được tiền hoàn. Cảm ơn bạn! 🙏 返金はいつですか？" },
};
export const HtmlIsShownAsText: Story = {
  args: { text: "<b>bold?</b> <script>alert('x')</script>" },
};
