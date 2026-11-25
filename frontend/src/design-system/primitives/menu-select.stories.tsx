import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, screen, userEvent, within } from "storybook/test";

import { MenuSelect } from "@/design-system/primitives/menu-select";

const meta = {
  title: "Design system/Primitives/MenuSelect",
  component: MenuSelect,
  args: {
    label: "Ticket status",
    options: [
      { value: "open", label: "Open" },
      { value: "awaiting_approval", label: "Awaiting approval" },
      { value: "escalated", label: "Escalated" },
      { value: "closed", label: "Closed" },
    ],
    value: "open",
    onChange: fn(),
  },
} satisfies Meta<typeof MenuSelect<string>>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Closed: Story = {};
export const OneOption: Story = { args: { options: [{ value: "open", label: "Open" }] } };
export const Open: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(
      within(canvasElement).getByRole("button", { name: "Ticket status: Open" }),
    );

    await expect(await screen.findByRole("menuitemradio", { name: "Open" })).toBeChecked();
  },
};
