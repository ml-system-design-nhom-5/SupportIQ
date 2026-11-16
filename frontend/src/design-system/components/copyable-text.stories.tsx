import type { Meta, StoryObj } from "@storybook/react-vite";

import { CopyableText } from "@/design-system/components/copyable-text";

const meta = {
  title: "Design system/Components/CopyableText",
  component: CopyableText,
  args: {
    label: "Your unsent text",
    children: "Hello Lan,\n\nyour refund for the headphones is under review.",
  },
} satisfies Meta<typeof CopyableText>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
