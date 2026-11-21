import type { Meta, StoryObj } from "@storybook/react-vite";

import { RelativeTimeText } from "@/design-system/components/relative-time-text";

/** The preview fixes now at 2026-11-05T09:00:00Z. */
const meta = {
  title: "Design system/Components/RelativeTimeText",
  component: RelativeTimeText,
  args: { timestamp: "2026-11-05T07:00:00Z" },
} satisfies Meta<typeof RelativeTimeText>;

export default meta;

type Story = StoryObj<typeof meta>;

export const HoursAgo: Story = {};
export const WeeksAgo: Story = { args: { timestamp: "2026-10-13T16:45:10Z" } };
