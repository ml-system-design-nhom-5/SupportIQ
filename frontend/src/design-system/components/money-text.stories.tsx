import type { Meta, StoryObj } from "@storybook/react-vite";

import { MoneyText } from "@/design-system/components/money-text";

const meta = {
  title: "Design system/Components/MoneyText",
  component: MoneyText,
  args: { money: { amountMinor: 8900, currency: "USD" } },
} satisfies Meta<typeof MoneyText>;

export default meta;

type Story = StoryObj<typeof meta>;

export const UsDollars: Story = {};
export const Cents: Story = { args: { money: { amountMinor: 5, currency: "USD" } } };
export const Zero: Story = { args: { money: { amountMinor: 0, currency: "USD" } } };
export const VietnameseDong: Story = { args: { money: { amountMinor: 890_000, currency: "VND" } } };
export const LargestAmount: Story = {
  args: { money: { amountMinor: 9_007_199_254_740_991, currency: "USD" } },
};
