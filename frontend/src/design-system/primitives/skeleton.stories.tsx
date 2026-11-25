import type { Meta, StoryObj } from "@storybook/react-vite";

import { Skeleton } from "@/design-system/primitives/skeleton";

const meta = {
  title: "Design system/Primitives/Skeleton",
  component: Skeleton,
} satisfies Meta<typeof Skeleton>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FullLine: Story = { args: { width: "full" } };
export const ThreeQuarterLine: Story = { args: { width: "three-quarters" } };
export const HalfLine: Story = { args: { width: "half" } };
export const ThirdLine: Story = { args: { width: "third" } };
export const Block: Story = { args: { height: "block" } };
