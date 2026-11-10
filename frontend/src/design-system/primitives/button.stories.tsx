import type { Meta, StoryObj } from "@storybook/react-vite";
import { Send } from "lucide-react";

import { Button } from "@/design-system/primitives/button";

const meta = {
  title: "Design system/Primitives/Button",
  component: Button,
  args: { children: "Send message" },
} satisfies Meta<typeof Button>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Primary: Story = { args: { variant: "primary" } };
export const Secondary: Story = { args: { variant: "secondary", children: "Contact support" } };
export const Danger: Story = { args: { variant: "danger", children: "Deactivate" } };
export const Ghost: Story = { args: { variant: "ghost", children: "Sign out" } };
export const TableRowSize: Story = { args: { size: "sm" } };
export const ShopSize: Story = { args: { variant: "primary", size: "lg" } };
export const WithIcon: Story = { args: { variant: "primary", size: "lg", leadingIcon: Send } };
export const Disabled: Story = { args: { variant: "primary", disabled: true } };
export const Pending: Story = {
  args: { variant: "primary", isPending: true, children: "Sending…" },
};
export const FullWidthOnPhone: Story = { args: { variant: "primary", width: "full-on-phone" } };
export const FullWidth: Story = {
  args: { variant: "primary", width: "full", children: "Sign in" },
};
