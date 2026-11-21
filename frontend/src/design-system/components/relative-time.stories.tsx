import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen } from "storybook/test";

import { RelativeTime } from "@/design-system/components/relative-time";

/** The preview fixes now at 2026-11-05T09:00:00Z. */
const meta = {
  title: "Design system/Components/RelativeTime",
  component: RelativeTime,
  args: { timestamp: "2026-11-05T08:59:30Z" },
} satisfies Meta<typeof RelativeTime>;

export default meta;

type Story = StoryObj<typeof meta>;

export const JustNow: Story = {};
export const MinutesAgo: Story = { args: { timestamp: "2026-11-05T08:42:00Z" } };
export const HoursAgo: Story = { args: { timestamp: "2026-11-05T07:00:00Z" } };
export const WeeksAgo: Story = { args: { timestamp: "2026-10-13T16:45:10Z" } };
export const AbsoluteTimeOnFocus: Story = {
  args: { timestamp: "2026-10-13T16:45:10Z" },
  play: async ({ userEvent }) => {
    await userEvent.tab();

    await expect(await screen.findByRole("tooltip")).toBeVisible();
  },
};
