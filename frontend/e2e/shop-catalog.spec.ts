/**
 * The catalog against the Prism mock: Products, Show more products, Product, and Support, with
 * axe on each screen and no sideways scrolling from 360 px.
 */
import { expect, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import {
  expectNoAccessibilityViolations,
  expectNoSidewaysScrolling,
} from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const listProductsRequest = { method: "GET", path: "/v1/shop/products" } as const;

test("a customer browses the catalog and opens a product", async ({ page }) => {
  const chooseProducts = await preferOutcome(page, listProductsRequest, "example=first-page");
  await createSessionCookie(page);

  await page.goto("/shop");
  await expect(page.getByRole("link", { name: "Desk lamp" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);

  chooseProducts("example=last-page");
  await page.getByRole("button", { name: "Show more products" }).click();
  await expect(page.getByRole("link", { name: "Wireless headphones" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Desk lamp" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Show more products" })).toBeHidden();

  await page.getByRole("link", { name: "Wireless headphones" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Wireless headphones" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);
});

test("a catalog that cannot load shows an error, and Try again loads it", async ({ page }) => {
  const chooseProducts = await preferOutcome(page, listProductsRequest, "code=503");
  await createSessionCookie(page);

  await page.goto("/shop");
  await expect(page.getByRole("heading", { name: "Products could not be loaded" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);

  chooseProducts("example=first-page");
  await page.getByRole("button", { name: "Try again" }).click();

  await expect(page.getByRole("link", { name: "Desk lamp" })).toBeVisible();
});

test("the built page keeps to its Content Security Policy (SEC-23)", async ({ page }) => {
  const consoleMessages: string[] = [];
  page.on("console", (message) => {
    consoleMessages.push(message.text());
  });
  await createSessionCookie(page);

  await page.goto("/shop/orders");
  await expect(page.getByRole("link", { name: /ORD-20990/ })).toBeVisible();

  expect(consoleMessages.join("\n")).not.toContain("Content Security Policy");
});

test("a customer opens Support and a ticket opens its order", async ({ page }) => {
  await createSessionCookie(page);

  await page.goto("/shop/support");
  await expect(page.getByRole("heading", { level: 1, name: "Support" })).toBeVisible();
  await expect(page.getByRole("link", { name: /TCK-1042/ })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);

  await page.getByRole("link", { name: /TCK-1042/ }).click();

  await expect(page).toHaveURL(/\/shop\/orders\/ORD-20931#ticket-TCK-1042$/);
});
