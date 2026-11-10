import type { Meta, StoryObj } from "@storybook/react-vite";
import { LayoutGrid, LifeBuoy, LogOut, Package, ShoppingBag, Users } from "lucide-react";
import { expect } from "storybook/test";

import { AccountLabel } from "@/design-system/components/account-label";
import { AppBar } from "@/design-system/components/app-bar";
import { Button } from "@/design-system/primitives/button";
import { NavItem } from "@/design-system/primitives/nav-item";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const signOut = (
  <Button variant="ghost" leadingIcon={LogOut}>
    Sign out
  </Button>
);

const meta = {
  title: "Design system/Components/AppBar",
  component: AppBar,
  parameters: { layout: "fullscreen" },
  args: { variant: "shop", brandName: "Demo Shop" },
} satisfies Meta<typeof AppBar>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ConsoleWithLongUnbrokenDisplayName: Story = {
  args: {
    variant: "console",
    brandName: "SupportIQ",
    areaName: "Console",
    account: (
      <>
        <AccountLabel displayName={"N".repeat(200)} roleLabel="Staff" />
        {signOut}
      </>
    ),
  },
  play: async ({ canvas, canvasElement }) => {
    const bar = canvas.getByRole("banner");

    await expect(bar.scrollHeight).toBeLessThanOrEqual(bar.clientHeight);
    await expectNoSidewaysOverflow(canvasElement);
  },
};
export const LongUnbrokenDisplayName: Story = {
  args: {
    brandIcon: ShoppingBag,
    account: (
      <>
        <AccountLabel displayName={"N".repeat(200)} />
        {signOut}
      </>
    ),
  },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
export const Shop: Story = {
  args: {
    brandIcon: ShoppingBag,
    navigation: (
      <>
        <NavItem to="/" icon={LayoutGrid} isExactMatch>
          Products
        </NavItem>
        <NavItem to="/shop/orders" icon={Package}>
          My orders
        </NavItem>
        <NavItem to="/shop/support" icon={LifeBuoy}>
          Support
        </NavItem>
      </>
    ),
    account: (
      <>
        <AccountLabel displayName="Linh Tran" />
        {signOut}
      </>
    ),
  },
};
export const ShopWithoutNavigation: Story = { args: { brandIcon: ShoppingBag } };
export const Console: Story = {
  args: {
    variant: "console",
    brandName: "SupportIQ",
    areaName: "Console",
    account: (
      <>
        <AccountLabel displayName="Mai Nguyen" roleLabel="Staff" />
        {signOut}
      </>
    ),
  },
};
export const Admin: Story = {
  args: {
    variant: "console",
    brandName: "SupportIQ",
    areaName: "Admin",
    navigation: (
      <NavItem to="/" icon={Users}>
        Accounts
      </NavItem>
    ),
    account: (
      <>
        <AccountLabel displayName="An Tran" roleLabel="Admin" />
        {signOut}
      </>
    ),
  },
};
