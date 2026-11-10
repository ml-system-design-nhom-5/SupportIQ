import type { Meta, StoryObj } from "@storybook/react-vite";
import { LayoutGrid, Package } from "lucide-react";

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
