import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { Chip } from "@/design-system/components/chip";
import { Cluster } from "@/design-system/primitives/cluster";

const meta = {
  title: "Design system/Components/Chip",
  component: Chip,
  args: { children: "Missing case info" },
} satisfies Meta<typeof Chip>;

export default meta;

type Story = StoryObj<typeof meta>;

export const EscalationReason: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(canvas.getByText("Missing case info")).toBeVisible();
    await expect(canvas.queryByRole("button")).not.toBeInTheDocument();
  },
};
export const SeveralEscalationReasons: Story = {
  render: () => (
    <Cluster>
      <Chip>Missing case info</Chip>
      <Chip>Case exception</Chip>
    </Cluster>
  ),
};
