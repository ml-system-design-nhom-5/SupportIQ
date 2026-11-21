import type { Meta, StoryObj } from "@storybook/react-vite";
import { TriangleAlert } from "lucide-react";

import { Tag } from "@/design-system/components/tag";

const meta = {
  title: "Design system/Components/Tag",
  component: Tag,
  args: { tone: "ai", children: "AI suggestion" },
} satisfies Meta<typeof Tag>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Ai: Story = {};
export const Neutral: Story = { args: { tone: "neutral", children: "This ticket" } };
export const WarningWithIcon: Story = {
  args: { tone: "warning", icon: TriangleAlert, children: "Low confidence" },
};
