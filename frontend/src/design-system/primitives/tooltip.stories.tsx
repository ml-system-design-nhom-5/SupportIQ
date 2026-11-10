import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, screen } from "storybook/test";

import { Tooltip } from "@/design-system/primitives/tooltip";

const meta = {
  title: "Design system/Primitives/Tooltip",
  component: Tooltip,
  args: { content: "2 Oct 2026, 19:30", children: "3 weeks ago" },
} satisfies Meta<typeof Tooltip>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Closed: Story = {};

export const OpenOnFocus: Story = {
  play: async ({ userEvent }) => {
    await userEvent.tab();

    await expect(await screen.findByRole("tooltip")).toHaveTextContent("2 Oct 2026, 19:30");
  },
};
