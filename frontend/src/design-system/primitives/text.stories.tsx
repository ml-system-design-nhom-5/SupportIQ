import type { Meta, StoryObj } from "@storybook/react-vite";

import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Primitives/Text",
  component: Text,
  args: { children: "Each message gets one reply from a person on our support team." },
} satisfies Meta<typeof Text>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ConsoleBody: Story = {};
export const ShopBody: Story = { args: { size: "base" } };
export const Muted: Story = { args: { tone: "muted" } };
export const Success: Story = { args: { tone: "success", children: "Message sent." } };
export const Warning: Story = { args: { tone: "warning", children: "Delayed" } };
export const Danger: Story = { args: { tone: "danger", children: "Your message was not sent." } };
export const Info: Story = { args: { tone: "info", children: "Received" } };
export const Small: Story = { args: { size: "xs" } };
export const Large: Story = { args: { size: "lg", children: "$89.00" } };
export const ExtraLarge: Story = { args: { size: "xl", children: "$89.00" } };
export const Truncated: Story = {
  args: {
    overflow: "truncate",
    children:
      "Hi, I sent back the headphones from order ORD-20931 almost two weeks ago and I still have not got my money back.",
  },
};
export const PreservedLineBreaksAndNonAscii: Story = {
  args: {
    size: "base",
    overflow: "preserve",
    children: "Xin chào,\ntôi chưa nhận được tiền hoàn cho đơn ORD-20931.\nCảm ơn! 😊",
  },
};
export const VeryLongWord: Story = {
  args: { size: "base", children: "a".repeat(200) },
};
