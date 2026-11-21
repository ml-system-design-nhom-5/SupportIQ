import type { Meta, StoryObj } from "@storybook/react-vite";

import { Breadcrumbs } from "@/design-system/components/breadcrumbs";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const meta = {
  title: "Design system/Components/Breadcrumbs",
  component: Breadcrumbs,
  args: {
    steps: [
      { label: "My orders", to: "/shop/orders" },
      { label: "ORD-20931", isIdentifier: true },
    ],
  },
} satisfies Meta<typeof Breadcrumbs>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithIdentifier: Story = {};
export const WithName: Story = {
  args: { steps: [{ label: "Products", to: "/shop" }, { label: "Wireless headphones" }] },
};
export const LongUnbrokenName: Story = {
  args: {
    steps: [{ label: "Products", to: "/shop" }, { label: "N".repeat(160) }],
  },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
export const ListOnly: Story = { args: { steps: [{ label: "My orders", to: "/shop/orders" }] } };
