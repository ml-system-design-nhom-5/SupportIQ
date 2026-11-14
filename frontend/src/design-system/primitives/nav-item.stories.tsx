import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChartColumn, Inbox, LayoutGrid, Package } from "lucide-react";
import { expect } from "storybook/test";

import { NavItem } from "@/design-system/primitives/nav-item";

const meta = {
  title: "Design system/Primitives/NavItem",
  component: NavItem,
  decorators: [
    (Story) => (
      <nav aria-label="Main">
        <Story />
      </nav>
    ),
  ],
} satisfies Meta<typeof NavItem>;

export default meta;

type Story = StoryObj<typeof meta>;

/** The preview router is at "/", so this entry is the current page. */
export const Current: Story = { args: { to: "/", icon: LayoutGrid, children: "Products" } };
export const NotCurrent: Story = {
  args: { to: "/shop/orders", icon: Package, children: "My orders" },
};
/** The area says the entry is not current, although the router is on its path. */
export const NotCurrentBySetting: Story = {
  args: { to: "/", icon: Inbox, isCurrent: false, children: "Tickets" },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("link", { name: "Tickets" })).not.toHaveAttribute("aria-current");
  },
};
/** The area says the entry is current, although the router is on another path. */
export const CurrentBySetting: Story = {
  args: { to: "/console/reports", icon: ChartColumn, isCurrent: true, children: "Reports" },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("link", { name: "Reports" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  },
};
