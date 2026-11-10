import type { Meta, StoryObj } from "@storybook/react-vite";
import { CircleCheck, Info, TriangleAlert } from "lucide-react";

import { InlineMessage } from "@/design-system/components/inline-message";

const meta = {
  title: "Design system/Components/InlineMessage",
  component: InlineMessage,
  args: {
    tone: "danger",
    icon: TriangleAlert,
    role: "alert",
    children: "The login name or the password is not correct.",
  },
} satisfies Meta<typeof InlineMessage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ErrorMessage: Story = {};
export const Hint: Story = {
  args: {
    tone: "muted",
    icon: Info,
    children: "Each message gets one reply from a person on our support team.",
  },
};
export const Confirmation: Story = {
  args: { tone: "success", icon: CircleCheck, role: "status", children: "Saved." },
};
