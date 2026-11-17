/**
 * The account menu of the app bar in tests (account management design, Account menu): open it and
 * choose an item, as a person does.
 */
import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

/** An item of the account menu. */
export type AccountMenuItem = "Change password" | "Sign out";

/**
 * Open the account menu in the app bar.
 *
 * @param user - The user-event instance.
 * @returns The open menu.
 */
export async function openAccountMenu(user: UserEvent): Promise<HTMLElement> {
  const bar = await screen.findByRole("banner");
  await user.click(within(bar).getByRole("button", { expanded: false }));
  return screen.findByRole("menu");
}

/**
 * Open the account menu in the app bar and choose an item.
 *
 * @param user - The user-event instance.
 * @param item - The item to choose.
 */
export async function chooseFromAccountMenu(user: UserEvent, item: AccountMenuItem): Promise<void> {
  const menu = await openAccountMenu(user);
  await user.click(within(menu).getByRole("menuitem", { name: item }));
}

/**
 * Switch dev mode in the account menu, where dev mode is available (UI-35).
 *
 * @param user - The user-event instance.
 */
export async function switchDevMode(user: UserEvent): Promise<void> {
  const menu = await openAccountMenu(user);
  await user.click(within(menu).getByRole("menuitemcheckbox", { name: "Dev mode" }));
}
