/**
 * The account menu of the app bar in the UI flow tests (account management design, Account menu).
 */
import type { Locator, Page } from "@playwright/test";

/**
 * Find the button that opens the account menu.
 *
 * @param page - The page.
 * @returns The menu button in the app bar.
 */
export function findAccountMenuButton(page: Page): Locator {
  return page.getByRole("banner").getByRole("button", { expanded: false });
}

/**
 * Open the account menu with a click and choose an item, as a person does.
 *
 * @param page - The page.
 * @param item - The name of the menu item.
 */
export async function chooseFromAccountMenu(
  page: Page,
  item: "Change password" | "Sign out",
): Promise<void> {
  await findAccountMenuButton(page).click();
  await page.getByRole("menuitem", { name: item }).click();
}
