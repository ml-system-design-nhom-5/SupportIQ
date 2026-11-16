/**
 * Dev mode in a production build (UI-35): the UI flow tests run against the production build that
 * the demo deployment serves (playwright.config.ts), where dev mode is not available unless
 * `VITE_DEV_MODE` says so. Staff and admins get neither the switch nor the developer details there.
 */
import { expect, test } from "@playwright/test";

import { findAccountMenuButton } from "./support/account-menu.ts";
import { DRAFT_READY_PATH, openTicket } from "./support/console-flows.ts";
import { preferOutcome } from "./support/mock-outcomes.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;

test("the production build offers staff no dev mode switch", async ({ page }) => {
  await openTicket(page, DRAFT_READY_PATH, { ticket: "example=draft-ready" });
  await expect(page.getByRole("region", { name: "AI draft" })).toBeVisible();

  await findAccountMenuButton(page).click();

  await expect(page.getByRole("menuitem", { name: "Change password" })).toBeVisible();
  await expect(page.getByRole("menuitemcheckbox")).toHaveCount(0);
});

test("the production build shows no developer details on a ticket", async ({ page }) => {
  await openTicket(page, DRAFT_READY_PATH, { ticket: "example=draft-ready" });

  await expect(page.getByRole("region", { name: "AI draft" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Developer details" })).toHaveCount(0);
});

test("the production build shows no developer details in the admin area", async ({ page }) => {
  await preferOutcome(page, getSessionRequest, "example=admin");
  await createSessionCookie(page);
  await page.goto("/admin/accounts");
  await expect(page.getByRole("heading", { level: 1, name: "Accounts" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Raw values" })).toHaveCount(0);

  await page.getByRole("banner").getByRole("link", { name: "Versions" }).click();

  await expect(page.getByRole("heading", { level: 1, name: "Versions in use" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Developer details" })).toHaveCount(0);
});
