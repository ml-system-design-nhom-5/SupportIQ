/**
 * The reply flows of the console against the Prism mock (console UI design, Flow, Actions, and
 * Action counts): the deliberate actions of each flow (UI-41), and the TEST-27 scenarios of the
 * reply area. Only the Send reply of the confirmation sends a reply (UI-17, FR-04). The mock is
 * stateless and answers with the example files, so a flow chooses the next answer of the ticket
 * when its write goes out, because the console loads the ticket again as soon as the write
 * succeeds.
 */
import { expect, type Page, test } from "@playwright/test";

import {
  changeTicketOnWrite,
  confirmSend,
  countActions,
  expectReplySent,
  openConfirmation,
  recordWrites,
  sendAndConfirm,
} from "./support/console-flows.ts";
import { type MockedRequest, preferOutcome } from "./support/mock-outcomes.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";
import { createSessionCookie } from "./support/sign-in.ts";

const getSessionRequest: MockedRequest = { method: "GET", path: "/v1/sessions/current" };
const listTicketsRequest: MockedRequest = { method: "GET", path: "/v1/console/tickets" };
const getTicketRequest: MockedRequest = { method: "GET", path: "/v1/console/tickets/*" };
const createSuggestionRequest: MockedRequest = {
  method: "POST",
  path: "/v1/console/tickets/*/suggestions",
};
const sendReplyRequest: MockedRequest = { method: "POST", path: "/v1/console/tickets/*/replies" };

/** The URL globs of the writes after which the ticket loads again. */
const CREATE_SUGGESTION_URL = "**/v1/console/tickets/*/suggestions";
const SEND_REPLY_URL = "**/v1/console/tickets/*/replies";

/** The paths of the tickets of the examples. */
const DRAFT_READY_PATH = "/console/tickets/TCK-1042";
const MANUAL_MODE_PATH = "/console/tickets/TCK-1050";
const AI_UNAVAILABLE_PATH = "/console/tickets/TCK-1038";

/** The current suggestion of the draft-ready example. */
const DRAFT_READY_SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";
/** The canonical `text` of the draft of the draft-ready example, which Send reply sends as is. */
const DRAFT_TEXT =
  "Hello Lan Tran, thank you for your patience.\n\nYour refund request for order ORD-20931 is under review. This sample sentence stands for a policy statement from the cited document.";
/** A sentence of the drafts of the draft-ready and intent-corrected examples. */
const DRAFT_SENTENCE = "Your refund request for order ORD-20931 is under review.";
/** The text that staff write themselves. */
const STAFF_TEXT = "Your refund is under review. We will write to you again when it is decided.";
/** The banner of a send whose outcome is unknown, such as after a lost connection (ERR-16). */
const UNKNOWN_OUTCOME_BANNER =
  "The reply may have been sent. We could not confirm it. Sending the same reply again is safe: the customer gets it once.";
/**
 * How far the clock of the page jumps after a failed send: far beyond the delay of an automatic
 * retry (ERR-13), so a retry would go out. The clock is fake, so no test waits in real time
 * (TEST-14).
 */
const RETRY_WAIT = "01:00";

/** The examples that a flow starts with, as `Prefer` values. */
type FlowExamples = {
  readonly ticket: string;
  /** The answer of `createSuggestion`; `example=intent-override` by default. */
  readonly suggestion?: string;
  /** The answer of `sendReply`; `example=from-ai-draft` by default. */
  readonly reply?: string;
};

/** The manual-mode ticket, whose reply staff write without a draft. */
const manualReplyExamples: FlowExamples = {
  ticket: "example=manual-mode",
  reply: "example=without-ai-draft",
};

/**
 * Sign in as staff, choose the examples of the flow, and open the ticket. The ticket loads as
 * closed once a reply goes out, because `sendReply` closes it (contract, `sendReply`).
 *
 * @param page - The page.
 * @param ticketPath - The path of the ticket.
 * @param examples - The `Prefer` values of the ticket and of the writes; the draft-ready ticket by
 *   default.
 * @returns A function that chooses the `Prefer` value of the later loads of the ticket.
 */
async function openTicket(
  page: Page,
  ticketPath: string,
  examples: FlowExamples = { ticket: "example=draft-ready" },
): Promise<(prefer: string) => void> {
  await preferOutcome(page, getSessionRequest, "example=staff");
  await preferOutcome(page, listTicketsRequest, "example=open-queue");
  await preferOutcome(
    page,
    createSuggestionRequest,
    examples.suggestion ?? "example=intent-override",
  );
  await preferOutcome(page, sendReplyRequest, examples.reply ?? "example=from-ai-draft");
  const chooseTicket = await preferOutcome(page, getTicketRequest, examples.ticket);
  await changeTicketOnWrite(page, SEND_REPLY_URL, { chooseTicket, prefer: "example=closed" });
  await createSessionCookie(page);
  await page.goto(ticketPath);
  return chooseTicket;
}

/**
 * Lose the connection for the first `sendReply` only, as when the network drops once, and let every
 * later one reach the mock. No response reaches the page, so the outcome is unknown (ERR-16).
 *
 * @param page - The page.
 * @returns The `Idempotency-Key` of every `sendReply` that the page sends, in order.
 */
async function loseFirstSend(page: Page): Promise<readonly (string | undefined)[]> {
  const keys: (string | undefined)[] = [];
  await page.route(SEND_REPLY_URL, async (route) => {
    keys.push(route.request().headers()["idempotency-key"]);
    await (keys.length === 1 ? route.abort("failed") : route.fallback());
  });
  return keys;
}

test("UI-41: a draft approved and sent takes 1 action (TEST-27)", async ({ page }) => {
  await openTicket(page, DRAFT_READY_PATH);
  const main = page.getByRole("main");
  await expect(main.getByRole("region", { name: "AI draft" })).toContainText(
    "1 warning to check before sending",
  );
  await expectNoAccessibilityViolations(page);
  const actions = countActions();

  await main.getByRole("checkbox", { name: /^I have checked this/ }).check();
  const confirmation = await openConfirmation(page, actions);
  await expectNoAccessibilityViolations(page);
  const body = await confirmSend(confirmation);

  expect(actions.count()).toBe(1);
  expect(body).toEqual({
    basis: "ai_draft",
    body: DRAFT_TEXT,
    suggestion_id: DRAFT_READY_SUGGESTION_ID,
    acknowledged_warning_ids: ["w1"],
  });
  await expectReplySent(page);
  await expectNoAccessibilityViolations(page);
});

test("UI-41: a draft edited and sent takes 2 actions (TEST-27)", async ({ page }) => {
  await openTicket(page, DRAFT_READY_PATH);
  const main = page.getByRole("main");
  const actions = countActions();

  await actions.click(main.getByRole("button", { name: "Edit draft" }));
  const editor = main
    .getByRole("region", { name: "Edit draft" })
    .getByRole("textbox", { name: "Reply to the customer" });
  await expect(editor).toHaveValue(DRAFT_TEXT);
  await expectNoAccessibilityViolations(page);
  await editor.fill(STAFF_TEXT);
  await main.getByRole("checkbox", { name: /^I have checked this/ }).check();
  const body = await sendAndConfirm(page, actions);

  expect(actions.count()).toBe(2);
  expect(body).toEqual({
    basis: "ai_draft",
    body: STAFF_TEXT,
    suggestion_id: DRAFT_READY_SUGGESTION_ID,
    acknowledged_warning_ids: ["w1"],
  });
  await expectReplySent(page);
});

test("UI-41: a draft rejected for one reason, with another reply sent, takes 3 actions", async ({
  page,
}) => {
  await openTicket(page, DRAFT_READY_PATH);
  const main = page.getByRole("main");
  const actions = countActions();

  await actions.click(main.getByRole("button", { name: "Reject draft" }));
  const rejected = main.getByRole("region", { name: "Draft rejected" });
  await rejected.getByRole("textbox", { name: "Reply to the customer" }).fill(STAFF_TEXT);
  await expect(main).toContainText("Choose why you rejected the draft to send the reply.");
  await actions.click(rejected.getByRole("button", { name: "Unsupported claim" }));
  await expect(main).not.toContainText("Choose why you rejected the draft");
  await expectNoAccessibilityViolations(page);
  const body = await sendAndConfirm(page, actions);

  expect(actions.count()).toBe(3);
  expect(body).toEqual({
    basis: "rejected_ai_draft",
    body: STAFF_TEXT,
    suggestion_id: DRAFT_READY_SUGGESTION_ID,
    staff_reason_codes: ["unsupported_claim"],
  });
  await expectReplySent(page);
});

test("TEST-27: an abstained ticket is handled manually, with a reply that staff write", async ({
  page,
}) => {
  // No example of getConsoleTicket abstains for a reason other than low confidence, so the
  // manual-mode example stands for a ticket that staff handle without a draft.
  await openTicket(page, MANUAL_MODE_PATH, manualReplyExamples);
  const manual = page.getByRole("main").getByRole("region", { name: "Manual handling" });
  await expect(manual).toContainText("Refund decision or dispute?");

  await manual.getByRole("textbox", { name: "Reply to the customer" }).fill(STAFF_TEXT);
  await expectNoAccessibilityViolations(page);
  const body = await sendAndConfirm(page);

  expect(body).toEqual({ basis: "no_ai_draft", body: STAFF_TEXT });
  await expectReplySent(page);
});

test("TEST-27: a low-confidence ticket gets a draft once staff confirm the intent", async ({
  page,
}) => {
  const chooseTicket = await openTicket(page, DRAFT_READY_PATH, {
    ticket: "example=abstained-low-confidence",
  });
  await changeTicketOnWrite(page, CREATE_SUGGESTION_URL, {
    chooseTicket,
    prefer: "example=draft-ready",
  });
  const main = page.getByRole("main");
  const draft = main.getByRole("region", { name: "AI draft" });
  await expect(draft).toContainText("No draft is created until you choose an intent.");
  await expect(main.getByRole("button", { name: "Send reply" })).toBeDisabled();
  const suggestions = recordWrites(page, "/suggestions");

  await main
    .getByRole("region", { name: "Choose an intent" })
    .getByRole("button", { name: "Use this intent: Refund status" })
    .click();

  await expect(draft).toContainText(DRAFT_SENTENCE);
  expect(suggestions).toEqual([{ intent_override: "refund_status" }]);
  await expect(main.getByRole("button", { name: "Edit draft" })).toBeEnabled();
});

test("TEST-27: an intent correction produces a new draft", async ({ page }) => {
  const chooseTicket = await openTicket(page, DRAFT_READY_PATH);
  await changeTicketOnWrite(page, CREATE_SUGGESTION_URL, {
    chooseTicket,
    prefer: "example=intent-corrected",
  });
  const main = page.getByRole("main");
  const suggestions = recordWrites(page, "/suggestions");

  await main.getByRole("button", { name: "Use Request refund 7%" }).click();

  await expect(main.getByRole("region", { name: "Intent", exact: true })).toContainText(
    "Chosen by staff",
  );
  const draft = main.getByRole("region", { name: "AI draft" });
  await expect(draft).toContainText(DRAFT_SENTENCE);
  await expect(draft).not.toContainText("1 warning to check before sending");
  expect(suggestions).toEqual([{ intent_override: "request_refund" }]);
  // The new draft has no warning, so Send reply needs no acknowledgement.
  await expect(main.getByRole("button", { name: "Send reply" })).toBeEnabled();
  await expectNoAccessibilityViolations(page);
});

test("TEST-27: Try AI again brings a draft once ai-service is available again", async ({
  page,
}) => {
  const chooseTicket = await openTicket(page, AI_UNAVAILABLE_PATH, {
    ticket: "example=ai-service-unavailable",
    suggestion: "example=retry",
  });
  await changeTicketOnWrite(page, CREATE_SUGGESTION_URL, {
    chooseTicket,
    prefer: "example=draft-ready",
  });
  const main = page.getByRole("main");
  await expect(main.getByRole("region", { name: "Manual handling" })).toContainText(
    "AI unavailable",
  );
  const suggestions = recordWrites(page, "/suggestions");

  await main.getByRole("button", { name: "Try AI again" }).click();

  await expect(main.getByRole("region", { name: "AI draft" })).toContainText(DRAFT_SENTENCE);
  expect(suggestions).toEqual([{}]);
  await expect(main.getByRole("region", { name: "Manual handling" })).toHaveCount(0);
});

test("TEST-27: a placeholder blocks Send reply until staff replace it (UI-43)", async ({
  page,
}) => {
  await openTicket(page, MANUAL_MODE_PATH, { ticket: "example=manual-mode" });
  const main = page.getByRole("main");
  const editor = main.getByRole("textbox", { name: "Reply to the customer" });
  const send = main.getByRole("button", { name: "Send reply" });

  await editor.fill("We sent the label to [EMAIL].");

  await expect(send).toBeDisabled();
  await expect(main).toContainText("Replace the highlighted text to send the reply.");
  await expect(main).toContainText("Personal data or reserved text: replace before sending.");
  await expect(main.locator("mark", { hasText: "[EMAIL]" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await editor.fill("We sent the label to your email address.");
  await expect(send).toBeEnabled();
  await expect(main.locator("mark")).toHaveCount(0);
});

test("UI-18: Send reply stays disabled until the warning is acknowledged", async ({ page }) => {
  await openTicket(page, DRAFT_READY_PATH);
  const main = page.getByRole("main");
  const send = main.getByRole("button", { name: "Send reply" });
  await expect(send).toBeDisabled();
  await expect(main).toContainText("Acknowledge 1 warning to send the reply.");

  await main.getByRole("checkbox", { name: /^I have checked this/ }).check();

  await expect(send).toBeEnabled();
});

test("TS-29: a lost send keeps the text, is not retried, and reuses its key", async ({ page }) => {
  await page.clock.install();
  await openTicket(page, MANUAL_MODE_PATH, manualReplyExamples);
  const editor = page.getByRole("main").getByRole("textbox", { name: "Reply to the customer" });
  await editor.fill(STAFF_TEXT);
  const sentKeys = await loseFirstSend(page);

  await sendAndConfirm(page);

  await expect(page.getByRole("alert")).toHaveText(UNKNOWN_OUTCOME_BANNER);
  await expect(editor).toHaveValue(STAFF_TEXT);
  await page.clock.fastForward(RETRY_WAIT);
  expect(sentKeys).toHaveLength(1);
  await expectNoAccessibilityViolations(page);

  const body = await sendAndConfirm(page);

  expect(body).toEqual({ basis: "no_ai_draft", body: STAFF_TEXT });
  expect(sentKeys).toEqual([expect.stringMatching(/^[0-9a-f-]{36}$/), sentKeys[0]]);
  await expectReplySent(page);
});
