import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { LoadMoreButton } from "@/design-system/components/load-more-button";

const meta = {
  title: "Design system/Components/LoadMoreButton",
  component: LoadMoreButton,
  args: { label: "Show more products", isLoading: false, onLoadMore: fn() },
} satisfies Meta<typeof LoadMoreButton>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Idle: Story = {};
export const Loading: Story = { args: { isLoading: true } };
export const ConsoleSize: Story = { args: { size: "md", label: "Show more accounts" } };
