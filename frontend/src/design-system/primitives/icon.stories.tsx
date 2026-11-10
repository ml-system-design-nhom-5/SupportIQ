import type { Meta, StoryObj } from "@storybook/react-vite";
import { CircleCheck } from "lucide-react";

import { Icon } from "@/design-system/primitives/icon";

const meta = {
  title: "Design system/Primitives/Icon",
  component: Icon,
  args: { icon: CircleCheck },
} satisfies Meta<typeof Icon>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Small: Story = {};
export const Medium: Story = { args: { size: "md" } };
export const Large: Story = { args: { size: "lg" } };
export const Muted: Story = { args: { tone: "muted" } };
export const Primary: Story = { args: { tone: "primary" } };
export const Success: Story = { args: { tone: "success" } };
export const Warning: Story = { args: { tone: "warning" } };
export const Danger: Story = { args: { tone: "danger" } };
export const Info: Story = { args: { tone: "info" } };
export const Ai: Story = { args: { tone: "ai" } };
