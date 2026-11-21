import type { Meta, StoryObj } from "@storybook/react-vite";

import { CenteredPanel } from "@/design-system/components/centered-panel";
import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Components/CenteredPanel",
  component: CenteredPanel,
  parameters: { layout: "fullscreen" },
  args: { children: <Text size="lg">SupportIQ Console</Text> },
} satisfies Meta<typeof CenteredPanel>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
