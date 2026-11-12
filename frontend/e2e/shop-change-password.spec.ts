/**
 * The own password change of a customer against the Prism mock (account management design,
 * Testing and evaluation): from the account menu of the shop to `/change-password` and back. The
 * main failure is a wrong current password, which shows at its field. The phone project runs it at
 * 360 px, where the menu button shows only its icon.
 */
import { expect, test } from "@playwright/test";

import { chooseFromAccountMenu } from "./support/account-menu.ts";
import { CURRENT_PASSWORD, fillPasswordChange, NEW_PASSWORD } from "./support/change-password.ts";
import { preferOutcome } from "./support/mock-outcomes.ts";
import {
  expectNoAccessibilityViolations,
  expectNoSidewaysScrolling,
} from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const changeOwnPasswordRequest = {
  method: "POST",
  path: "/v1/sessions/current/password-changes",
} as const;

test("a customer changes the password from the account menu and goes back", async ({ page }) => {
  await createSessionCookie(page);
  await page.goto("/shop/orders");
  await expect(page.getByRole("heading", { level: 1, name: "My orders" })).toBeVisible();

  await chooseFromAccountMenu(page, "Change password");

  await expect(page).toHaveURL(/\/change-password$/);
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);
  await fillPasswordChange(page);
  await expect(page.getByRole("checkbox", { name: "Sign out of my other sessions" })).toBeChecked();
  const [request] = await Promise.all([
    page.waitForRequest((sent) => sent.method() === "POST"),
    page.getByRole("button", { name: "Change password" }).click(),
  ]);

  await expect(page.getByRole("status")).toHaveText(
    "Your password was changed. Your other sessions were signed out.",
  );
  expect(new URL(request.url()).pathname).toBe(changeOwnPasswordRequest.path);
  expect(request.postDataJSON()).toEqual({
    current_password: CURRENT_PASSWORD,
    new_password: NEW_PASSWORD,
    is_signed_out_elsewhere: true,
  });
  expect(request.headers()["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);

  await page.getByRole("button", { name: "Go back" }).click();

  await expect(page).toHaveURL(/\/shop\/orders$/);
});

test("a wrong current password shows at its field, which is cleared and focused", async ({
  page,
}) => {
  await preferOutcome(
    page,
    changeOwnPasswordRequest,
    "code=422, example=current-password-incorrect",
  );
  await createSessionCookie(page);
  await page.goto("/change-password");
  await fillPasswordChange(page);

  await page.getByRole("button", { name: "Change password" }).click();

  const currentPassword = page.getByLabel("Current password", { exact: true });
  await expect(currentPassword).toHaveAccessibleDescription("The current password is not correct.");
  await expect(currentPassword).toHaveValue("");
  await expect(currentPassword).toBeFocused();
  await expectNoAccessibilityViolations(page);
});
