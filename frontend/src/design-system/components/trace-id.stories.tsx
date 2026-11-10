import type { Meta, StoryObj } from "@storybook/react-vite";

import { TraceId } from "@/design-system/components/trace-id";

const meta = {
  title: "Design system/Components/TraceId",
  component: TraceId,
  args: { traceId: "4bf92f3577b34da6a3ce929d0e0e4736" },
} satisfies Meta<typeof TraceId>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
