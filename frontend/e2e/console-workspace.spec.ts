/**
 * The console flows against the Prism mock: the inbox, a ticket with a ready draft, its citations,
 * its KB document version, and its order, and the states of manual handling, an empty queue, an
 * error, and a role without the console (console UI design). The mock is stateless and answers with
 * the example files, so each flow chooses its examples with the `Prefer` header.
 */
import { expect, type Page, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const listTicketsRequest = { method: "GET", path: "/v1/console/tickets" } as const;
const getTicketRequest = { method: "GET", path: "/v1/console/tickets/*" } as const;

/**
 * Sign in with the session of an example and choose the examples of the console.
 *
 * @param page - The page.
 * @param examples - The `Prefer` values of the session, the queue, and the ticket.
 */
async function prepareConsole(
  page: Page,
  examples: { readonly session?: string; readonly queue?: string; readonly ticket?: string } = {},
): Promise<void> {
  await preferOutcome(page, getSessionRequest, examples.session ?? "example=staff");
  await preferOutcome(page, listTicketsRequest, examples.queue ?? "example=open-queue");
  await preferOutcome(page, getTicketRequest, examples.ticket ?? "example=draft-ready");
  await createSessionCookie(page);
}

test("staff open a ticket from the inbox and check its draft against its sources", async ({
  page,
}) => {
  await prepareConsole(page);
  await page.goto("/console");
  const inbox = page.getByRole("complementary", { name: "Inbox" });
  await expect(page.getByRole("heading", { level: 1, name: "Select a ticket" })).toBeVisible();
  await expectNoAccessibilityViolations(page);

  const viewRecorded = page.waitForRequest(
    (request) => request.method() === "POST" && request.url().endsWith("/views"),
  );
  await inbox.getByRole("link", { name: /TCK-1042/ }).click();

  const viewRequest = await viewRecorded;
  expect(viewRequest.headers()["idempotency-key"]).toMatch(/^[0-9a-f-]{36}$/);
  await expect(page).toHaveURL(/\/console\/tickets\/TCK-1042$/);
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();
  await expect(main.getByRole("region", { name: "AI draft" })).toContainText(
    "1 warning to check before sending",
  );
  await expectNoAccessibilityViolations(page);

  await main
    .getByRole("region", { name: "AI draft" })
    .getByRole("button", { name: "Source 1: Sample refund document" })
    .click();
  const sheet = page.getByRole("dialog", { name: "Sample refund document" });
  await expect(sheet).toContainText("Policy owner (sample)");
  await expectNoAccessibilityViolations(page);
  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(
    main.getByRole("region", { name: "AI draft" }).getByRole("button", { name: /^Source 1/ }),
  ).toBeFocused();

  await main.getByRole("button", { name: /^ORD-20931 Delivered/ }).click();
  const orders = page.getByRole("dialog", { name: "Orders of this customer" });
  await expect(orders).toContainText("From order records, not AI");
  await expectNoAccessibilityViolations(page);
});

test("a ticket whose AI failed is handled manually, with the reminder", async ({ page }) => {
  await prepareConsole(page, { ticket: "example=ai-service-unavailable" });
  await page.goto("/console/tickets/TCK-1038");

  const manual = page.getByRole("main").getByRole("region", { name: "Manual handling" });
  await expect(manual).toContainText("AI unavailable");
  await expect(manual).toContainText("Refund decision or dispute?");
  await expectNoAccessibilityViolations(page);
});

test("a ticket in manual mode shows no AI panel", async ({ page }) => {
  await prepareConsole(page, { ticket: "example=manual-mode" });
  await page.goto("/console/tickets/TCK-1049");

  await expect(page.getByRole("main")).toContainText("No order attached");
  await expect(page.getByRole("main").getByRole("region", { name: "AI draft" })).toHaveCount(0);
  await expectNoAccessibilityViolations(page);
});

test("a ticket that abstained for low confidence offers the top three intents", async ({
  page,
}) => {
  await prepareConsole(page, { ticket: "example=abstained-low-confidence" });
  await page.goto("/console/tickets/TCK-1042");

  await expect(
    page.getByRole("main").getByRole("region", { name: "Choose an intent" }).getByRole("listitem"),
  ).toHaveCount(3);
  await expect(page.getByRole("main")).toContainText(
    "No draft is created until you choose an intent.",
  );
  await expectNoAccessibilityViolations(page);
});

test("an empty queue says so in the inbox and next to it", async ({ page }) => {
  await prepareConsole(page, { queue: "example=empty" });
  await page.goto("/console");

  await expect(page.getByRole("heading", { level: 1, name: "No open tickets" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
});

test("a ticket that could not load shows the error with a trace ID", async ({ page }) => {
  await prepareConsole(page, { ticket: "code=500" });
  await page.goto("/console/tickets/TCK-1042");

  await expect(
    page.getByRole("heading", { level: 1, name: "This ticket could not be loaded" }),
  ).toBeVisible();
  await expect(page.getByText(/Details: trace/)).toBeVisible();
  await expectNoAccessibilityViolations(page);
});

test("a manager reads the closed queue, newest first", async ({ page }) => {
  await prepareConsole(page, { session: "example=manager", queue: "example=closed" });
  await page.goto("/console?status=closed");

  const inbox = page.getByRole("complementary", { name: "Inbox" });
  await expect(inbox.getByRole("button", { name: "Ticket status: Closed" })).toBeVisible();
  await expect(inbox.getByText("Newest first")).toBeVisible();
  await expect(inbox.getByRole("link", { name: /TCK-1017/ })).toHaveAttribute(
    "href",
    "/console/tickets/TCK-1017?status=closed",
  );
});

test("an account without the console sees the permission-denied state", async ({ page }) => {
  await prepareConsole(page, { session: "example=customer", queue: "code=403" });
  await page.goto("/console");

  await expect(
    page.getByRole("heading", { level: 1, name: "The console is for support accounts" }),
  ).toBeVisible();
  await expectNoAccessibilityViolations(page);
});

test("the view is recorded once for each opening of a ticket", async ({ page }) => {
  await prepareConsole(page);
  const requests: string[] = [];
  page.on("request", (request) => {
    requests.push(`${request.method()} ${new URL(request.url()).pathname}`);
  });
  await page.goto("/console/tickets/TCK-1042");
  await expect(page.getByRole("heading", { level: 1, name: "Ticket TCK-1042" })).toBeVisible();

  const secondView = page.waitForRequest((request) =>
    request.url().endsWith("/v1/console/tickets/TCK-1038/views"),
  );
  await page
    .getByRole("complementary", { name: "Inbox" })
    .getByRole("link", { name: /TCK-1038/ })
    .click();
  await secondView;

  expect(requests.filter((request) => request.endsWith("/views"))).toEqual([
    "POST /v1/console/tickets/TCK-1042/views",
    "POST /v1/console/tickets/TCK-1038/views",
  ]);
});
