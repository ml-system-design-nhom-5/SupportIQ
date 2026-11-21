import type { Meta, StoryObj } from "@storybook/react-vite";

import { DateText } from "@/design-system/components/date-text";

const meta = {
  title: "Design system/Components/DateText",
  component: DateText,
  args: { timestamp: "2026-10-02T19:30:00Z" },
} satisfies Meta<typeof DateText>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
