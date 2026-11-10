/**
 * The admin flow against the Prism mock: change a role after the confirmation. The main failure is
 * a `422` for the last active manager, whose message is shown. The mock is stateless, so the test
 * checks the request and the reload of the list, not a changed row.
 */
import { expect, type Page, test } from "@playwright/test";

import { loseConnection, preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const changeStatusRequest = {
  method: "POST",
  path: "/v1/admin/accounts/*/status-changes",
} as const;
const changeRoleRequest = { method: "POST", path: "/v1/admin/accounts/*/role-changes" } as const;

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
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/v1/admin/accounts",
    ),
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
    page.waitForResponse(
      (response) =>
        response.request().method() === "GET" &&
        new URL(response.url()).pathname === "/v1/admin/accounts",
    ),
    dialog.getByRole("button", { name: "Make manager" }).click(),
  ]);

  const banner = page.getByRole("alert");
  await expect(banner).toContainText("Mai Nguyen may have been made a manager.");
  await expect(banner).toContainText("it is safe to try again");
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
