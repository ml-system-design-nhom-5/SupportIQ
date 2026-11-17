/**
 * The progress of a suggestion against the Prism mock (ADR-0022, statement 9). Prism does not
 * serve the stream, so the workspace takes its fallback: it loads the ticket once after the stream
 * fails, and then every 30 s while a part is `pending`. The clock of the page is fake, so the test
 * does not wait in real time.
 */
import { expect, type Request, test } from "@playwright/test";

import { preferOutcome } from "./support/mock-outcomes.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest = { method: "GET", path: "/v1/sessions/current" } as const;
const listTicketsRequest = { method: "GET", path: "/v1/console/tickets" } as const;
const getTicketRequest = { method: "GET", path: "/v1/console/tickets/*" } as const;

/** The fallback poll of the workspace (src/features/console-tickets/model/polling.ts). */
const FALLBACK_POLL_MS = 30_000;

/** The path of the workspace read of the ticket of the examples. */
const TICKET_READ_PATH = "/v1/console/tickets/TCK-1042";

/**
 * Tell whether a request reads the workspace of the ticket.
 *
 * @param request - A request of the page.
 * @returns True for `getConsoleTicket` of TCK-1042.
 */
function isTicketRead(request: Request): boolean {
  return request.method() === "GET" && new URL(request.url()).pathname === TICKET_READ_PATH;
}

test("a workspace whose stream cannot run loads the ticket again after 30 s", async ({ page }) => {
  await page.clock.install();
  const ticketReads: Request[] = [];
  page.on("request", (request) => {
    if (isTicketRead(request)) {
      ticketReads.push(request);
    }
  });
  await preferOutcome(page, getSessionRequest, "example=staff");
  await preferOutcome(page, listTicketsRequest, "example=open-queue");
  const preferTicket = await preferOutcome(page, getTicketRequest, "example=suggestion-pending");
  await createSessionCookie(page);
  await page.goto("/console/tickets/TCK-1042");
  const draft = page.getByRole("region", { name: "AI draft" });
  await expect(draft).toContainText("Generating draft");
  // The load after the stream failed.
  await expect.poll(() => ticketReads.length).toBe(2);

  preferTicket("example=draft-ready");
  await page.clock.fastForward(FALLBACK_POLL_MS);

  await expect(draft).toContainText("Draft ready");
  expect(ticketReads).toHaveLength(3);
});
