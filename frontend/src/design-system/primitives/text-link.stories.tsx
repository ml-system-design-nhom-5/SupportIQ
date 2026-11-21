import type { Meta, StoryObj } from "@storybook/react-vite";

import { TextLink } from "@/design-system/primitives/text-link";

const meta = {
  title: "Design system/Primitives/TextLink",
  component: TextLink,
  args: { to: "/shop/products/PRD-1002", children: "Wireless headphones" },
} satisfies Meta<typeof TextLink>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Strong: Story = { args: { emphasis: "strong" } };
