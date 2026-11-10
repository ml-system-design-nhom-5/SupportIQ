import type { Meta, StoryObj } from "@storybook/react-vite";

import { Heading } from "@/design-system/primitives/heading";

const meta = {
  title: "Design system/Primitives/Heading",
  component: Heading,
  args: { level: 1, children: "My orders" },
} satisfies Meta<typeof Heading>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Page: Story = {};
export const Section: Story = { args: { size: "section", children: "Support for this order" } };
export const Item: Story = { args: { size: "item", children: "Wireless headphones" } };
