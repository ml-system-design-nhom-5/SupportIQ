import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChartColumn, Inbox, LayoutGrid, Package } from "lucide-react";
import { MemoryRouter } from "react-router";
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
/** An entry that matches its exact path only, on that path. */
export const CurrentOnExactPath: Story = {
  args: { to: "/", icon: LayoutGrid, current: { by: "exact-path" }, children: "Products" },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("link", { name: "Products" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  },
};
/** An entry that matches its exact path only, on a path below it. */
export const NotCurrentBelowExactPath: Story = {
  args: { to: "/shop", icon: LayoutGrid, current: { by: "exact-path" }, children: "Products" },
  parameters: { hasOwnRouter: true },
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/shop/orders"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("link", { name: "Products" })).not.toHaveAttribute(
      "aria-current",
    );
  },
};
/** The area says the entry is not current, although the router is on its path. */
export const NotCurrentByArea: Story = {
  args: { to: "/", icon: Inbox, current: { by: "area", isCurrent: false }, children: "Tickets" },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("link", { name: "Tickets" })).not.toHaveAttribute("aria-current");
  },
};
/** The area says the entry is current, although the router is on another path. */
export const CurrentByArea: Story = {
  args: {
    to: "/console/reports",
    icon: ChartColumn,
    current: { by: "area", isCurrent: true },
    children: "Reports",
  },
  play: async ({ canvas }) => {
    await expect(canvas.getByRole("link", { name: "Reports" })).toHaveAttribute(
      "aria-current",
      "page",
    );
  },
};
