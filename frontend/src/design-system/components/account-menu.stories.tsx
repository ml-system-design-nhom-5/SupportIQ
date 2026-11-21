import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, screen } from "storybook/test";

import { AccountMenu } from "@/design-system/components/account-menu";

const meta = {
  title: "Design system/Components/AccountMenu",
  component: AccountMenu,
  args: {
    variant: "console",
    displayName: "Mai Nguyen",
    roleLabel: "Staff",
    isSigningOut: false,
    onChangePassword: fn(),
    onSignOut: fn(),
  },
} satisfies Meta<typeof AccountMenu>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Open the menu as a person does, and wait for its items. */
const openMenu: Story["play"] = async ({ canvas, userEvent, args }) => {
  await userEvent.click(
    canvas.getByRole("button", { name: `${args.displayName} · ${args.roleLabel}` }),
  );

  await expect(await screen.findByRole("menuitem", { name: "Change password" })).toBeVisible();
  await expect(screen.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
};

/**
 * Open the menu with the dev mode item, and check that it announces the state of dev mode.
 *
 * @param isOn - The state that the item announces.
 * @returns The play function of the story.
 */
function openMenuWithDevMode(isOn: boolean): NonNullable<Story["play"]> {
  return async ({ canvas, userEvent, args }) => {
    await userEvent.click(
      canvas.getByRole("button", { name: `${args.displayName} · ${args.roleLabel}` }),
    );

    const devModeItem = await screen.findByRole("menuitemcheckbox", { name: "Dev mode" });
    await expect(devModeItem).toBeVisible();
    await expect(devModeItem).toHaveAttribute("aria-checked", String(isOn));
  };
}

const customer = { variant: "shop", displayName: "Lan Tran", roleLabel: "Customer" } as const;
const staff = { variant: "console", displayName: "Mai Nguyen", roleLabel: "Staff" } as const;
const manager = { variant: "console", displayName: "Hoa Pham", roleLabel: "Manager" } as const;
const admin = { variant: "console", displayName: "Quang Vo", roleLabel: "Admin" } as const;

export const CustomerClosed: Story = { args: customer };
export const CustomerOpen: Story = { args: customer, play: openMenu };
export const StaffClosed: Story = { args: staff };
export const StaffOpen: Story = { args: staff, play: openMenu };
export const ManagerClosed: Story = { args: manager };
export const ManagerOpen: Story = { args: manager, play: openMenu };
export const AdminClosed: Story = { args: admin };
export const AdminOpen: Story = { args: admin, play: openMenu };
/** Where dev mode is available (UI-35), the menu holds its switch; here it is off. */
export const DevModeOff: Story = {
  args: { ...staff, devMode: { isOn: false, onChange: fn() } },
  play: openMenuWithDevMode(false),
};
export const DevModeOn: Story = {
  args: { ...staff, devMode: { isOn: true, onChange: fn() } },
  play: openMenuWithDevMode(true),
};
