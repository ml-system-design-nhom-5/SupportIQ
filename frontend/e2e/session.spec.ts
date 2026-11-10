/**
 * The session against the Prism mock: a refused sign-in, sign-out, and a session that expires in
 * the middle of a task. The first flow of a successful sign-in is in shop-order.spec.ts.
 */
import { expect, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie, submitSignIn } from "./support/sign-in.ts";

const createSessionRequest = { method: "POST", path: "/v1/sessions" } as const;
const listOrdersRequest = { method: "GET", path: "/v1/shop/orders" } as const;

test("a refused sign-in says why, stays on the form, and keeps the login name", async ({
  page,
}) => {
  await preferOutcome(page, createSessionRequest, "code=401, example=invalid-credentials");

  await page.goto("/sign-in");
  await submitSignIn(page);

  await expect(page.getByRole("alert")).toHaveText(
    "The login name or the password is not correct.",
  );
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByRole("textbox", { name: "Login name" })).toHaveValue("customer-1");
  await expectNoAccessibilityViolations(page);
});

test("a customer signs out and reaches sign-in without a return path", async ({ page }) => {
  await createSessionCookie(page);
  await page.goto("/shop/orders");
  await expect(page.getByRole("heading", { level: 1, name: "My orders" })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();

  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByRole("textbox", { name: "Login name" })).toBeVisible();
});

test("an expired session opens sign-in once, and sign-in returns to the page", async ({ page }) => {
  const chooseOrders = await preferOutcome(page, listOrdersRequest, "example=first-page");
  await createSessionCookie(page);
  await page.goto("/shop/orders");
  await expect(page.getByRole("link", { name: /ORD-20990/ })).toBeVisible();

  chooseOrders("code=401");
  await page.getByRole("button", { name: "Show more orders" }).click();

  await expect(page).toHaveURL(/\/sign-in\?returnTo=%2Fshop%2Forders$/);
  chooseOrders("example=first-page");
  await submitSignIn(page);

  await expect(page).toHaveURL(/\/shop\/orders$/);
  await expect(page.getByRole("link", { name: /ORD-20990/ })).toBeVisible();
});
