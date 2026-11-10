import type { Meta, StoryObj } from "@storybook/react-vite";

import { ProductDetails } from "@/design-system/components/product-details";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const meta = {
  title: "Design system/Shop/ProductDetails",
  component: ProductDetails,
  args: {
    name: "Wireless headphones",
    category: "Audio",
    price: { amountMinor: 8900, currency: "USD" },
    description: "Over-ear headphones with a 30-hour battery.",
  },
} satisfies Meta<typeof ProductDetails>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const LongUnbrokenText: Story = {
  args: { name: "N".repeat(160), category: "C".repeat(160), description: "D".repeat(400) },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
export const LongDescription: Story = {
  args: { description: `${"A long product description. ".repeat(40)}\nSecond line.` },
};
