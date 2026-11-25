import type { Meta, StoryObj } from "@storybook/react-vite";

import { SessionLoading } from "@/features/session/components/session-loading";

const meta = {
  title: "Session/SessionLoading",
  component: SessionLoading,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof SessionLoading>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Loading: Story = {};
