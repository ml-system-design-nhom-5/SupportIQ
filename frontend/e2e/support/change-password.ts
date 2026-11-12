/**
 * The form of `/change-password` in the UI flow tests (account management design, Change password
 * page). The passwords are visibly fake: the Prism mock accepts any that match the contract.
 */
import type { Page } from "@playwright/test";

export const CURRENT_PASSWORD = "not-the-old-password";
export const NEW_PASSWORD = "not-the-new-password";

/**
 * Fill the current password and the new password twice, as a person does.
 *
 * @param page - A page on `/change-password`.
 */
export async function fillPasswordChange(page: Page): Promise<void> {
  await page.getByLabel("Current password", { exact: true }).fill(CURRENT_PASSWORD);
  await page.getByLabel("New password", { exact: true }).fill(NEW_PASSWORD);
  await page.getByLabel("Confirm new password", { exact: true }).fill(NEW_PASSWORD);
}
