import type { Meta, StoryObj } from "@storybook/react-vite";
import { LayoutGrid, LifeBuoy, Package, ShoppingBag, Users } from "lucide-react";
import { expect, fn } from "storybook/test";

import { AccountMenu, type AccountMenuProps } from "@/design-system/components/account-menu";
import { AppBar } from "@/design-system/components/app-bar";
import { NavItem } from "@/design-system/primitives/nav-item";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

/**
 * Render the account menu of a story.
 *
 * @param account - The variant, the display name, and the role label.
 * @returns The closed menu.
 */
function renderAccountMenu(
  account: Pick<AccountMenuProps, "variant" | "displayName" | "roleLabel">,
) {
  return <AccountMenu {...account} isSigningOut={false} onChangePassword={fn()} onSignOut={fn()} />;
}

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
    account: renderAccountMenu({
      variant: "console",
      displayName: "N".repeat(200),
      roleLabel: "Staff",
    }),
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
    account: renderAccountMenu({
      variant: "shop",
      displayName: "N".repeat(200),
      roleLabel: "Customer",
    }),
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
    account: renderAccountMenu({
      variant: "shop",
      displayName: "Linh Tran",
      roleLabel: "Customer",
    }),
  },
};
export const ShopWithoutNavigation: Story = { args: { brandIcon: ShoppingBag } };
export const Console: Story = {
  args: {
    variant: "console",
    brandName: "SupportIQ",
    areaName: "Console",
    account: renderAccountMenu({
      variant: "console",
      displayName: "Mai Nguyen",
      roleLabel: "Staff",
    }),
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
    account: renderAccountMenu({ variant: "console", displayName: "An Tran", roleLabel: "Admin" }),
  },
};
