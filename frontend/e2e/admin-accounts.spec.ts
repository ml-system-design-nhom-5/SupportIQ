/**
 * The admin flows against the Prism mock: change a role after the confirmation, create an account
 * with the suggested password, and reset the password of a `staff` account. The main failures are
 * a `422` for the last active manager, whose message is shown, and a lost connection, after which
 * the screen says that the change, the creation, or the reset may have happened (account
 * management design, Errors and guardrails). The mock is stateless, so the tests check the
 * requests and the reload of the list, not a changed row.
 */
import { expect, type Locator, type Page, type Response, test } from "@playwright/test";

import { loseConnection, preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const changeStatusRequest = {
  method: "POST",
  path: "/v1/admin/accounts/*/status-changes",
} as const;
const changeRoleRequest = { method: "POST", path: "/v1/admin/accounts/*/role-changes" } as const;
const createAccountRequest = { method: "POST", path: "/v1/admin/accounts" } as const;
const resetPasswordRequest = {
  method: "POST",
  path: "/v1/admin/accounts/*/password-resets",
} as const;

/**
 * Open Accounts with the session of the admin example.
 *
 * @param page - The page.
 */
async function openAccountsAsAdmin(page: Page): Promise<void> {
  await preferOutcome(page, getSessionRequest, "example=admin");
  await createSessionCookie(page);
  await page.goto("/admin");
  await expect(page).toHaveURL(/\/admin\/accounts$/);
  await expect(page.getByRole("heading", { level: 1, name: "Accounts" })).toBeVisible();
  await expect(page.getByRole("rowheader", { name: "Mai Nguyen" })).toBeVisible();
}

/**
 * Wait for the next answer to the list of accounts, such as the reload after a write.
 *
 * @param page - The page.
 * @returns The response of `listAdminAccounts`.
 */
function waitForAccountList(page: Page): Promise<Response> {
  return page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === "/v1/admin/accounts",
  );
}

/**
 * Open the reset dialog of Mai Nguyen, a `staff` account of the list example.
 *
 * @param page - A page on Accounts.
 * @returns The dialog.
 */
async function openResetDialog(page: Page): Promise<Locator> {
  const row = page.getByRole("row", { name: /Mai Nguyen/ });
  await row.getByRole("button", { name: /Reset password/ }).click();
  const dialog = page.getByRole("dialog", { name: "Reset the password of Mai Nguyen?" });
  await expect(dialog).toBeVisible();
  return dialog;
}

test("an admin changes a role after the confirmation", async ({ page }) => {
  await openAccountsAsAdmin(page);
  await expectNoAccessibilityViolations(page);

  const row = page.getByRole("row", { name: /Mai Nguyen/ });
  await row.getByRole("button", { name: /Make manager/ }).click();
  const dialog = page.getByRole("alertdialog", { name: "Make Mai Nguyen a manager?" });
  await expect(dialog).toBeVisible();
  await expectNoAccessibilityViolations(page);
  const [changeRequest, reloadResponse] = await Promise.all([
    page.waitForRequest((sent) => sent.method() === "POST"),
    waitForAccountList(page),
    dialog.getByRole("button", { name: "Make manager" }).click(),
  ]);

  await expect(dialog).toBeHidden();
  expect(new URL(changeRequest.url()).pathname).toMatch(/\/role-changes$/);
  expect(changeRequest.postDataJSON()).toEqual({ role: "manager" });
  expect(changeRequest.headers()["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
  expect(reloadResponse.status()).toBe(200);
});

test("the last active manager cannot be deactivated, and the banner says why", async ({ page }) => {
  await preferOutcome(page, changeStatusRequest, "code=422, example=last-active-manager");
  await openAccountsAsAdmin(page);

  const row = page.getByRole("row", { name: /Hoa Pham/ });
  await row.getByRole("button", { name: /Deactivate/ }).click();
  const dialog = page.getByRole("alertdialog", { name: "Deactivate Hoa Pham?" });
  await dialog.getByRole("button", { name: "Deactivate" }).click();

  const banner = page.getByRole("alert");
  await expect(banner).toContainText("Hoa Pham was not deactivated.");
  await expect(banner).toContainText("This change would leave no active manager.");
  await expect(dialog).toBeHidden();
  await expectNoAccessibilityViolations(page);
});

test("a lost connection says that the change may have happened, and the list loads again", async ({
  page,
}) => {
  await openAccountsAsAdmin(page);
  await loseConnection(page, changeRoleRequest);

  const row = page.getByRole("row", { name: /Mai Nguyen/ });
  await row.getByRole("button", { name: /Make manager/ }).click();
  const dialog = page.getByRole("alertdialog", { name: "Make Mai Nguyen a manager?" });
  const [reloadResponse] = await Promise.all([
    waitForAccountList(page),
    dialog.getByRole("button", { name: "Make manager" }).click(),
  ]);

  const banner = page.getByRole("alert");
  await expect(banner).toContainText("Mai Nguyen may have been made a manager.");
  await expect(banner).toContainText("it is safe to try again");
  expect(reloadResponse.status()).toBe(200);
  await expectNoAccessibilityViolations(page);
});

test("an admin creates an account with the suggested password and learns its login name", async ({
  page,
}) => {
  await openAccountsAsAdmin(page);
  await page.getByRole("button", { name: "Create account" }).click();
  const dialog = page.getByRole("dialog", { name: "Create an account" });
  await dialog.getByRole("textbox", { name: "Display name" }).fill("Lan Do");
  const suggestedPassword = await dialog.getByLabel("Password", { exact: true }).inputValue();

  const [request] = await Promise.all([
    page.waitForRequest((sent) => sent.method() === "POST"),
    dialog.getByRole("button", { name: "Create account" }).click(),
  ]);

  await expect(page.getByRole("status").filter({ hasText: "Account created:" })).toHaveText(
    "Account created: Lan Do, login name staff-5.",
  );
  expect(request.postDataJSON()).toEqual({
    role: "staff",
    display_name: "Lan Do",
    password: suggestedPassword,
  });
  expect(request.headers()["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
  await expectNoAccessibilityViolations(page);
});

test("a lost connection says that the account may have been created, and the list loads again", async ({
  page,
}) => {
  await openAccountsAsAdmin(page);
  await loseConnection(page, createAccountRequest);
  await page.getByRole("button", { name: "Create account" }).click();
  const dialog = page.getByRole("dialog", { name: "Create an account" });
  await dialog.getByRole("textbox", { name: "Display name" }).fill("Lan Do");

  const [reloadResponse] = await Promise.all([
    waitForAccountList(page),
    dialog.getByRole("button", { name: "Create account" }).click(),
  ]);

  await expect(dialog.getByRole("alert")).toContainText("The account may have been created.");
  await expect(dialog.getByRole("alert")).toContainText(
    "Select Create account again without editing the fields to find out.",
  );
  expect(reloadResponse.status()).toBe(200);
  await expectNoAccessibilityViolations(page);
});

test("an admin resets the password of a staff account, and the banner says so", async ({
  page,
}) => {
  await openAccountsAsAdmin(page);
  const dialog = await openResetDialog(page);

  const [reloadResponse] = await Promise.all([
    waitForAccountList(page),
    dialog.getByRole("button", { name: "Reset password" }).click(),
  ]);

  await expect(dialog).toBeHidden();
  await expect(page.getByRole("status").filter({ hasText: "was reset." })).toHaveText(
    "The password of Mai Nguyen was reset. Mai Nguyen was signed out of every session.",
  );
  expect(reloadResponse.status()).toBe(200);
  await expectNoAccessibilityViolations(page);
});

test("a lost connection says that the password may have been reset, and the list loads again", async ({
  page,
}) => {
  await openAccountsAsAdmin(page);
  await loseConnection(page, resetPasswordRequest);
  const dialog = await openResetDialog(page);

  const [reloadResponse] = await Promise.all([
    waitForAccountList(page),
    dialog.getByRole("button", { name: "Reset password" }).click(),
  ]);

  await expect(dialog.getByRole("alert")).toContainText("The password may have been reset.");
  await expect(dialog.getByRole("alert")).toContainText(
    "Select Reset password again without editing the fields to find out.",
  );
  expect(reloadResponse.status()).toBe(200);
  await expectNoAccessibilityViolations(page);
});

test("another role sees the permission-denied state of the admin area", async ({ page }) => {
  await preferOutcome(
    page,
    { method: "GET", path: "/v1/admin/accounts" },
    "code=403, example=forbidden-role",
  );
  await createSessionCookie(page);

  await page.goto("/admin/accounts");

  await expect(
    page.getByRole("heading", { level: 1, name: "The admin area is for admin accounts" }),
  ).toBeVisible();
  await expect(page.getByRole("main").getByRole("button", { name: "Sign out" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
});
