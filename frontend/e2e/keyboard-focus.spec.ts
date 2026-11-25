/**
 * The keyboard stays in place in the production build (UI-30): a button that waits for `backend`
 * keeps the focus, a confirmation returns it to where it was, and a success that replaces a form
 * takes it. Only a browser shows this, because jsdom does not drop the focus from a disabled
 * button.
 */
import { expect, type Locator, type Page, test } from "@playwright/test";

import { findAccountMenuButton } from "./support/account-menu.ts";
import { fillPasswordChange } from "./support/change-password.ts";
import { preferOutcome } from "./support/mock-outcomes.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const listProductsRequest = { method: "GET", path: "/v1/shop/products" } as const;
const MESSAGE_BOX_NAME = "Write to support about this order";

/**
 * Activate a control with the keyboard.
 *
 * @param page - The page.
 * @param control - The control.
 */
async function pressEnterOn(page: Page, control: Locator): Promise<void> {
  await control.focus();
  await page.keyboard.press("Enter");
}

/**
 * Open the order ORD-20990 with a message in the box.
 *
 * @param page - The page.
 * @returns The message box.
 */
async function openOrderWithMessage(page: Page): Promise<Locator> {
  await createSessionCookie(page);
  await page.goto("/shop/orders/ORD-20990");
  const messageBox = page.getByRole("textbox", { name: MESSAGE_BOX_NAME });
  await messageBox.fill("Hello");
  return messageBox;
}

/**
 * Open Accounts as an admin, and the confirmation of Make manager.
 *
 * @param page - The page.
 * @returns The button that opened the dialog, and the dialog.
 */
async function openConfirmation(page: Page) {
  await preferOutcome(page, { method: "GET", path: "/v1/sessions/current" }, "example=admin");
  await createSessionCookie(page);
  await page.goto("/admin/accounts");
  const row = page.getByRole("row", { name: /Mai Nguyen/ });
  const opener = row.getByRole("button", { name: /Make manager/ });
  await pressEnterOn(page, opener);
  const dialog = page.getByRole("alertdialog", { name: "Make Mai Nguyen a manager?" });
  await expect(dialog).toBeVisible();
  return { opener, dialog };
}

test("Send message moves the focus to the message box after a success", async ({ page }) => {
  const messageBox = await openOrderWithMessage(page);

  await pressEnterOn(page, page.getByRole("button", { name: "Send message" }));

  await expect(page.getByRole("status").filter({ hasText: "Message sent." })).toBeVisible();
  await expect(messageBox).toBeFocused();
});

test("Send message moves the focus to the message box after a failure", async ({ page }) => {
  await preferOutcome(page, { method: "POST", path: "/v1/shop/tickets" }, "code=422");
  const messageBox = await openOrderWithMessage(page);

  await pressEnterOn(page, page.getByRole("button", { name: "Send message" }));

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(messageBox).toBeFocused();
  await expect(messageBox).toHaveValue("Hello");
});

test("Show more keeps the focus while there is a next page", async ({ page }) => {
  await preferOutcome(page, listProductsRequest, "example=first-page");
  await createSessionCookie(page);
  await page.goto("/shop");
  const showMore = page.getByRole("button", { name: "Show more products" });

  await pressEnterOn(page, showMore);

  await expect(showMore).toHaveAttribute("aria-busy", "false");
  await expect(showMore).toBeFocused();
});

test("Show more keeps the focus when the next page fails", async ({ page }) => {
  const chooseProducts = await preferOutcome(page, listProductsRequest, "example=first-page");
  await createSessionCookie(page);
  await page.goto("/shop");
  const showMore = page.getByRole("button", { name: "Show more products" });
  await expect(showMore).toBeVisible();
  chooseProducts("code=422");

  await pressEnterOn(page, showMore);

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(showMore).toBeFocused();
});

test("Show more on the last page leaves the place at the end of the list", async ({ page }) => {
  const chooseProducts = await preferOutcome(page, listProductsRequest, "example=first-page");
  await createSessionCookie(page);
  await page.goto("/shop");
  const showMore = page.getByRole("button", { name: "Show more products" });
  await expect(showMore).toBeVisible();
  chooseProducts("example=last-page");

  await pressEnterOn(page, showMore);

  const lastProduct = page.getByRole("link", { name: "Wireless headphones" });
  await expect(lastProduct).toBeVisible();
  await expect(page.getByRole("button", { name: "Loading…" })).toBeHidden();
  await page.keyboard.press("Shift+Tab");
  await expect(lastProduct).toBeFocused();
});

test("Try again keeps the place when the list fails, and when it loads", async ({ page }) => {
  const chooseProducts = await preferOutcome(page, listProductsRequest, "code=422");
  await createSessionCookie(page);
  await page.goto("/shop");
  const tryAgain = page.getByRole("button", { name: "Try again" });
  await expect(tryAgain).toBeVisible();

  await Promise.all([
    page.waitForResponse(
      (response) => new URL(response.url()).pathname === listProductsRequest.path,
    ),
    pressEnterOn(page, tryAgain),
  ]);
  await expect(tryAgain).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(tryAgain).toBeFocused();

  chooseProducts("example=first-page");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("link", { name: "Desk lamp" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Desk lamp" })).toBeFocused();
});

test("Sign in keeps the focus when the sign-in is refused", async ({ page }) => {
  await preferOutcome(page, { method: "POST", path: "/v1/sessions" }, "code=401");
  await page.goto("/sign-in");
  await page.getByRole("textbox", { name: "Login name" }).fill("customer-1");
  await page.getByLabel("Password", { exact: true }).fill("not-a-real-password");
  const signIn = page.getByRole("button", { name: "Sign in" });

  await pressEnterOn(page, signIn);

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(signIn).toBeFocused();
});

test("Sign out in the account menu returns the focus to the menu button when it fails", async ({
  page,
}) => {
  await preferOutcome(page, { method: "DELETE", path: "/v1/sessions/current" }, "code=503");
  await createSessionCookie(page);
  await page.goto("/shop");
  const menuButton = findAccountMenuButton(page);
  await pressEnterOn(page, menuButton);

  await pressEnterOn(page, page.getByRole("menuitem", { name: "Sign out" }));

  await expect(page.getByRole("alert")).toBeVisible();
  await expect(menuButton).toBeFocused();
});

test("a successful password change moves the focus to the success notice", async ({ page }) => {
  await createSessionCookie(page);
  await page.goto("/change-password");
  await fillPasswordChange(page);

  await pressEnterOn(page, page.getByRole("button", { name: "Change password" }));

  await expect(
    page.getByRole("status").filter({ hasText: "Your password was changed." }),
  ).toBeFocused();
});

test("Escape returns the focus to the button that opened the dialog", async ({ page }) => {
  const { opener, dialog } = await openConfirmation(page);

  await page.keyboard.press("Escape");

  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test("Cancel returns the focus to the button that opened the dialog", async ({ page }) => {
  const { opener, dialog } = await openConfirmation(page);

  await pressEnterOn(page, dialog.getByRole("button", { name: "Cancel" }));

  await expect(dialog).toBeHidden();
  await expect(opener).toBeFocused();
});

test("a confirmed change moves the focus to the row, because its button changed", async ({
  page,
}) => {
  const { dialog } = await openConfirmation(page);

  await pressEnterOn(page, dialog.getByRole("button", { name: "Make manager" }));

  await expect(dialog).toBeHidden();
  const rowHeader = page.getByRole("rowheader", { name: "Mai Nguyen" });
  await expect(rowHeader).toBeFocused();
  await expect(rowHeader).toHaveCSS("outline-style", "solid");
});

test("the account menu and the show and hide toggle work with the keyboard only", async ({
  page,
}) => {
  await createSessionCookie(page);
  await page.goto("/shop");
  const menuButton = findAccountMenuButton(page);
  await menuButton.focus();

  await page.keyboard.press("Enter");
  await expect(page.getByRole("menuitem", { name: "Change password" })).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Sign out" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("menu")).toBeHidden();
  await expect(menuButton).toBeFocused();
  await page.keyboard.press("ArrowDown");
  await expect(page.getByRole("menuitem", { name: "Change password" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/change-password$/);

  const currentPassword = page.getByLabel("Current password", { exact: true });
  await currentPassword.focus();
  await page.keyboard.type("not-a-real-password");
  await page.keyboard.press("Tab");
  const toggle = page.getByRole("button", { name: "Show password" }).first();
  await expect(toggle).toBeFocused();
  await page.keyboard.press("Space");
  await expect(toggle).toHaveAttribute("aria-pressed", "true");
  await expect(currentPassword).toHaveAttribute("type", "text");
  await expect(currentPassword).toHaveValue("not-a-real-password");
  await page.keyboard.press("Space");
  await expect(toggle).toHaveAttribute("aria-pressed", "false");
  await expect(currentPassword).toHaveAttribute("type", "password");
});
