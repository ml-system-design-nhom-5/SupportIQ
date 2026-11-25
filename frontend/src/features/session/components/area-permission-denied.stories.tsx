import type { Meta, StoryObj } from "@storybook/react-vite";

import { AreaPermissionDenied } from "@/features/session/components/area-permission-denied";

const meta = {
  title: "Session/AreaPermissionDenied",
  component: AreaPermissionDenied,
  args: { area: "shop" },
} satisfies Meta<typeof AreaPermissionDenied>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Shop: Story = { args: { traceId: "b7ad6b7169203331b7ad6b7169203331" } };
export const Admin: Story = {
  args: { area: "admin", traceId: "b7ad6b7169203331b7ad6b7169203331" },
};
export const WithoutTraceId: Story = {};
