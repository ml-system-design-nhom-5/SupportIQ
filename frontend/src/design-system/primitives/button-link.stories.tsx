import type { Meta, StoryObj } from "@storybook/react-vite";
import { ArrowLeft } from "lucide-react";

import { ButtonLink } from "@/design-system/primitives/button-link";

const meta = {
  title: "Design system/Primitives/ButtonLink",
  component: ButtonLink,
  args: { to: "/shop/orders", children: "Back to My orders" },
} satisfies Meta<typeof ButtonLink>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Secondary: Story = {};
export const Primary: Story = { args: { variant: "primary" } };
export const ShopSizeWithIcon: Story = { args: { size: "lg", leadingIcon: ArrowLeft } };
