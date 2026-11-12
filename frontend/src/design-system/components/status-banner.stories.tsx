import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { StatusBanner } from "@/design-system/components/status-banner";
import { Button } from "@/design-system/primitives/button";

const meta = {
  title: "Design system/Components/StatusBanner",
  component: StatusBanner,
  args: {
    tone: "success",
    lead: "Message sent.",
    children: "A person from our support team replies here.",
  },
} satisfies Meta<typeof StatusBanner>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Success: Story = {};
export const SuccessWithTheFocus: Story = {
  args: { lead: "Your password was changed.", children: undefined, focusTargetId: "changed" },
  play: async ({ canvasElement }) => {
    const banner = within(canvasElement).getByRole("status");

    banner.focus();

    await expect(banner).toHaveFocus();
  },
};
export const Info: Story = { args: { tone: "info", lead: "Read only.", children: "No change." } };
export const Warning: Story = {
  args: { tone: "warning", lead: "Out of date.", children: "Reload the list." },
};
export const DangerWithTraceId: Story = {
  args: {
    tone: "danger",
    lead: "Hoa Pham was not deactivated.",
    children: "This change would leave no active manager. Make another account a manager first.",
    traceId: "eb211c80319c0af7651916cd43dd8448",
  },
};
export const DangerWithAction: Story = {
  args: {
    tone: "danger",
    lead: "Minh Le was not changed.",
    children: "The list may be out of date. Reload the list, then try again.",
    action: <Button>Reload list</Button>,
  },
};
