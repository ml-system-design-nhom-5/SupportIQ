import type { Meta, StoryObj } from "@storybook/react-vite";

import { VisuallyHidden } from "@/design-system/primitives/visually-hidden";

const meta = {
  title: "Design system/Primitives/VisuallyHidden",
  component: VisuallyHidden,
  args: { children: "Order status" },
} satisfies Meta<typeof VisuallyHidden>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Nothing shows: screen readers read "Order status". */
export const Default: Story = {};
