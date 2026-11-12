/**
 * The account menu of the app bar in tests (account management design, Account menu): open it and
 * choose an item, as a person does.
 */
import { screen, within } from "@testing-library/react";
import type { UserEvent } from "@testing-library/user-event";

/** An item of the account menu. */
export type AccountMenuItem = "Change password" | "Sign out";

/**
 * Open the account menu in the app bar and choose an item.
 *
 * @param user - The user-event instance.
 * @param item - The item to choose.
 */
export async function chooseFromAccountMenu(user: UserEvent, item: AccountMenuItem): Promise<void> {
  const bar = await screen.findByRole("banner");
  await user.click(within(bar).getByRole("button", { expanded: false }));
  await user.click(await screen.findByRole("menuitem", { name: item }));
}
