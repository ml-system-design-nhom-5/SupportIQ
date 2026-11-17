import type { Meta, StoryObj } from "@storybook/react-vite";

import { ConfidenceMeter } from "@/design-system/components/confidence-meter";

const meta = {
  title: "Design system/Components/ConfidenceMeter",
  component: ConfidenceMeter,
  args: { band: "high", probability: 0.91 },
} satisfies Meta<typeof ConfidenceMeter>;

export default meta;

type Story = StoryObj<typeof meta>;

export const High: Story = {};
export const Medium: Story = { args: { band: "medium", probability: 0.64 } };
export const Low: Story = { args: { band: "low", probability: 0.41 } };
