/**
 * The customer flow against the Prism mock: sign in, open an order, send a message, and see it as
 * received. The main failures are a `503` while sending, which keeps the text, and a lost
 * connection, after which the same text is sent again with the same key.
 */
import { expect, type Page, type Request, test } from "@playwright/test";

import { loseConnection, preferOutcome } from "./support/mock-outcomes.ts";
import {
  expectNoAccessibilityViolations,
  expectNoSidewaysScrolling,
} from "./support/page-checks.ts";
import { submitSignIn } from "./support/sign-in.ts";

const listTicketsRequest = { method: "GET", path: "/v1/shop/tickets" } as const;
const createTicketRequest = { method: "POST", path: "/v1/shop/tickets" } as const;
const MESSAGE = "Can I also return the charging cable?";

/**
 * Sign in from a protected page and open the order ORD-20990.
 *
 * @param page - The page.
 */
async function signInAndOpenOrder(page: Page): Promise<void> {
  await page.goto("/shop/orders");
  await expect(page).toHaveURL(/\/sign-in\?returnTo=%2Fshop%2Forders$/);
  await expectNoAccessibilityViolations(page);
  await submitSignIn(page);

  await expect(page).toHaveURL(/\/shop\/orders$/);
  await expect(page.getByRole("heading", { level: 1, name: "My orders" })).toBeVisible();
  await expect(page.getByRole("link", { name: /ORD-20990/ })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);

  await page.getByRole("link", { name: /ORD-20990/ }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Order ORD-20990" })).toBeVisible();
}

test("a customer signs in, opens an order, sends a message, and sees it as received", async ({
  page,
}) => {
  const chooseTickets = await preferOutcome(page, listTicketsRequest, "example=empty");

  await signInAndOpenOrder(page);
  await expectNoAccessibilityViolations(page);
  await expectNoSidewaysScrolling(page);

  const messageBox = page.getByRole("textbox", { name: "Write to support about this order" });
  await page.getByRole("button", { name: "Contact support" }).click();
  await expect(messageBox).toBeFocused();
  await messageBox.fill(MESSAGE);
  chooseTickets("example=last-page");
  const [request] = await Promise.all([
    page.waitForRequest((sent) => sent.method() === "POST"),
    page.getByRole("button", { name: "Send message" }).click(),
  ]);

  await expect(page.getByRole("status")).toContainText("Message sent.");
  await expect(messageBox).toHaveValue("");
  await expect(page.getByText("Received", { exact: true })).toBeVisible();
  expect(request.postDataJSON()).toEqual({ order_id: "ORD-20990", message: MESSAGE });
  expect(request.headers()["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
  await expectNoAccessibilityViolations(page);
});

test("a failed send shows the reason and keeps the text", async ({ page }) => {
  await preferOutcome(page, listTicketsRequest, "example=empty");
  await preferOutcome(page, createTicketRequest, "code=503");

  await signInAndOpenOrder(page);
  const messageBox = page.getByRole("textbox", { name: "Write to support about this order" });
  await messageBox.fill(MESSAGE);
  await page.getByRole("button", { name: "Send message" }).click();

  await expect(page.getByRole("alert")).toContainText("Your message was not sent.");
  await expect(page.getByRole("alert")).toContainText("Details: trace");
  await expect(messageBox).toHaveValue(MESSAGE);
  await expectNoAccessibilityViolations(page);
});

test("a lost connection says that the message may have arrived, and it is sent again safely", async ({
  page,
}) => {
  await preferOutcome(page, listTicketsRequest, "example=empty");
  await signInAndOpenOrder(page);
  const messageBox = page.getByRole("textbox", { name: "Write to support about this order" });
  await messageBox.fill(MESSAGE);
  const sendMessage = page.getByRole("button", { name: "Send message" });
  const isSend = (request: Request) => request.method() === "POST";
  const restoreConnection = await loseConnection(page, createTicketRequest);

  const [lostRequest] = await Promise.all([page.waitForRequest(isSend), sendMessage.click()]);

  await expect(page.getByRole("alert")).toContainText("Your message may have arrived.");
  await expect(page.getByRole("alert")).not.toContainText("was not sent");
  await expect(messageBox).toHaveValue(MESSAGE);
  await expectNoAccessibilityViolations(page);

  await restoreConnection();
  const [sentRequest] = await Promise.all([page.waitForRequest(isSend), sendMessage.click()]);

  await expect(page.getByRole("status")).toContainText("Message sent.");
  expect(sentRequest.headers()["idempotency-key"]).toBe(lostRequest.headers()["idempotency-key"]);
});
