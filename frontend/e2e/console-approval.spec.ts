/**
 * The approval and escalation flows of the console against the Prism mock (console UI design,
 * Flow, Actions, Action counts, and States): Submit for approval with and without the authority
 * flag and in manual handling, a reply proposal that a manager sends as is or edited (TEST-27), a
 * ticket that staff read while it awaits approval, Escalate ticket with its dialog, and a manager's
 * reply to an escalated ticket. Only the Send reply of the confirmation sends a reply (UI-17,
 * FR-04); Submit for approval and Escalate ticket reach no customer. The mock is stateless, so each
 * flow chooses the next answer of the ticket when its write goes out.
 */
import { expect, type Locator, type Page, test } from "@playwright/test";

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
const createProposalRequest: MockedRequest = {
  method: "POST",
  path: "/v1/console/tickets/*/reply-proposals",
};
const sendReplyRequest: MockedRequest = { method: "POST", path: "/v1/console/tickets/*/replies" };
const createEscalationRequest: MockedRequest = {
  method: "POST",
  path: "/v1/console/tickets/*/escalations",
};

/** The paths of the tickets of the examples; the authority-required ticket also awaits approval. */
const AUTHORITY_REQUIRED_PATH = "/console/tickets/TCK-1046";
const DRAFT_READY_PATH = "/console/tickets/TCK-1042";
const MANUAL_MODE_PATH = "/console/tickets/TCK-1050";
const ESCALATED_PATH = "/console/tickets/TCK-1047";
/** The URL glob of the loads of the draft-ready ticket. */
const DRAFT_READY_TICKET_URL = "**/v1/console/tickets/TCK-1042";

/** The current suggestions of the examples. */
const AUTHORITY_SUGGESTION_ID = "8d3a1e5c-7b9f-4a2d-8e6c-0f2b4d6a8c41";
const DRAFT_READY_SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";
const ESCALATED_SUGGESTION_ID = "5a7c9e1b-3d5f-4a7c-9e1b-3d5f7a9c1e64";
/** The proposal of the awaiting-approval example, and its text: the AI draft unchanged. */
const PROPOSAL_ID = "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52";
const PROPOSAL_TEXT =
  "Hello Lan Tran, thank you for your patience.\n\nYour refund request for order ORD-20931 is under review. This sample sentence stands for a policy statement from the cited document.";
/** The note of the escalated example. */
const ESCALATION_NOTE = "The customer asks to talk to a person.";
/** The text that staff write themselves. */
const STAFF_TEXT = "Your request is with a manager. We will write to you again once it is decided.";
/** The text that a manager writes. */
const MANAGER_TEXT =
  "A manager checked your request. We will write to you again with the decision.";
/** The line above the buttons when a ticket is read-only for staff. */
const READ_ONLY_LINE = "This ticket is read-only for you. A manager sends the reply.";
/** The More item of Submit for approval, named by its two lines. */
const SUBMIT_MENU_ITEM = "Submit for approval A manager sends the reply";

/** The write of a flow, its example, and the `Prefer` value of the ticket after it. */
type FlowWrite = {
  readonly request: MockedRequest;
  readonly prefer: string;
  /** Absent when the flow answers the later loads of the ticket itself. */
  readonly ticketAfter?: string;
};

/** The examples that a flow starts with, as `Prefer` values. */
type FlowExamples = {
  /** The session; `example=staff` by default. */
  readonly session?: string;
  /** The queue of the inbox; `example=open-queue` by default. */
  readonly queue?: string;
  readonly ticket: string;
  /** The write of the flow; absent when the flow only reads. */
  readonly write?: FlowWrite;
};

/** A proposal on the AI draft; the ticket then awaits approval, read-only for staff. */
const proposalOnDraft: FlowWrite = {
  request: createProposalRequest,
  prefer: "example=from-ai-draft",
  ticketAfter: "example=read-only-for-staff",
};
/** A manager on the ticket that awaits approval, which is closed once the reply is sent. */
const managerOnProposal: FlowExamples = {
  session: "example=manager",
  queue: "example=awaiting-approval",
  ticket: "example=awaiting-approval",
  write: {
    request: sendReplyRequest,
    prefer: "example=from-reply-proposal",
    ticketAfter: "example=closed",
  },
};

/**
 * Sign in, choose the examples of the flow, and open the ticket.
 *
 * @param page - The page.
 * @param ticketPath - The path of the ticket.
 * @param examples - The `Prefer` values of the session, the queue, the ticket, and the write.
 */
async function openTicket(page: Page, ticketPath: string, examples: FlowExamples): Promise<void> {
  await preferOutcome(page, getSessionRequest, examples.session ?? "example=staff");
  await preferOutcome(page, listTicketsRequest, examples.queue ?? "example=open-queue");
  const chooseTicket = await preferOutcome(page, getTicketRequest, examples.ticket);
  const { write } = examples;
  if (write !== undefined) {
    await preferOutcome(page, write.request, write.prefer);
  }
  if (write?.ticketAfter !== undefined) {
    await changeTicketOnWrite(page, `**${write.request.path}`, {
      chooseTicket,
      prefer: write.ticketAfter,
    });
  }
  await createSessionCookie(page);
  await page.goto(ticketPath);
}

/**
 * Answer the loads of the draft-ready ticket after its escalation with the `escalated` example as
 * staff see it. The example is the view of a manager, so its `allowed_actions` is emptied: an
 * escalated ticket is read-only for staff (console UI design, Flow).
 *
 * @param page - The page.
 */
async function showEscalatedToStaff(page: Page): Promise<void> {
  let isEscalated = false;
  await page.route(`**${createEscalationRequest.path}`, async (route) => {
    isEscalated = true;
    await route.fallback();
  });
  await page.route(DRAFT_READY_TICKET_URL, async (route) => {
    if (!isEscalated) {
      await route.fallback();
      return;
    }
    const response = await route.fetch({
      headers: { ...route.request().headers(), prefer: "example=escalated" },
    });
    const workspace: unknown = await response.json();
    if (typeof workspace !== "object" || workspace === null) {
      throw new Error("The example is not a ticket workspace.");
    }
    await route.fulfill({ response, json: { ...workspace, allowed_actions: [] } });
  });
}

/**
 * Read where an element starts on the screen.
 *
 * @param element - A visible element.
 * @returns The distance from the top of the viewport to its top edge.
 */
async function getTop(element: Locator): Promise<number> {
  const box = await element.boundingBox();
  if (box === null) {
    throw new Error("The element is not visible.");
  }
  return box.y;
}

/**
 * Check that the ticket, loaded again after Submit for approval, awaits approval and is read-only
 * for staff, with the focus on the heading of the reply area (console UI design, Flow; UI-30).
 *
 * @param page - The page.
 */
async function expectAwaitingApproval(page: Page): Promise<void> {
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { name: "Reply for approval" })).toBeFocused();
  const reply = main.getByRole("region", { name: "Reply for approval" });
  await expect(reply).toContainText(READ_ONLY_LINE);
  await expect(reply.getByRole("textbox")).toHaveCount(0);
}

test("UI-41: a draft edited and submitted for approval takes 2 actions when authority is required", async ({
  page,
}) => {
  await openTicket(page, AUTHORITY_REQUIRED_PATH, {
    ticket: "example=authority-required",
    write: proposalOnDraft,
  });
  const main = page.getByRole("main");
  await expect(main.getByRole("button", { name: "Send reply" })).toHaveCount(0);
  await expect(main).toContainText("A manager sends the reply on this ticket.");
  await expectNoAccessibilityViolations(page);
  const proposals = recordWrites(page, "/reply-proposals");
  const actions = countActions();

  await actions.click(main.getByRole("button", { name: "Edit draft" }));
  await main.getByRole("textbox", { name: "Reply to the customer" }).fill(STAFF_TEXT);
  await actions.click(main.getByRole("button", { name: "Submit for approval" }));

  await expectAwaitingApproval(page);
  expect(actions.count()).toBe(2);
  expect(proposals).toEqual([
    {
      basis: "ai_draft",
      body: STAFF_TEXT,
      suggestion_id: AUTHORITY_SUGGESTION_ID,
      acknowledged_warning_ids: [],
    },
  ]);
  await expectNoAccessibilityViolations(page);
});

test("UI-41: a draft edited and submitted for approval through More takes 3 actions", async ({
  page,
}) => {
  await openTicket(page, DRAFT_READY_PATH, {
    ticket: "example=draft-ready",
    write: proposalOnDraft,
  });
  const main = page.getByRole("main");
  await expect(main.getByRole("button", { name: "Submit for approval" })).toHaveCount(0);
  const proposals = recordWrites(page, "/reply-proposals");
  const actions = countActions();

  await actions.click(main.getByRole("button", { name: "Edit draft" }));
  await main.getByRole("textbox", { name: "Reply to the customer" }).fill(STAFF_TEXT);
  await main.getByRole("checkbox", { name: /^I have checked this/ }).check();
  await actions.click(main.getByRole("button", { name: "More actions" }));
  const submit = page.getByRole("menuitem", { name: SUBMIT_MENU_ITEM });
  await expect(submit).toBeVisible();
  await expectNoAccessibilityViolations(page);
  await actions.click(submit);

  await expectAwaitingApproval(page);
  expect(actions.count()).toBe(3);
  expect(proposals).toEqual([
    {
      basis: "ai_draft",
      body: STAFF_TEXT,
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
      acknowledged_warning_ids: ["w1"],
    },
  ]);
});

test("UI-26: in manual handling, Submit for approval is a button that submits the written reply", async ({
  page,
}) => {
  await openTicket(page, MANUAL_MODE_PATH, {
    ticket: "example=manual-mode",
    write: { ...proposalOnDraft, prefer: "example=without-ai-draft" },
  });
  const manual = page.getByRole("main").getByRole("region", { name: "Manual handling" });
  const submit = manual.getByRole("button", { name: "Submit for approval" });
  await expect(submit).toBeDisabled();
  await expect(manual).toContainText("Write a reply to send it or to submit it for approval.");
  await expect(manual.getByRole("button", { name: "More actions" })).toHaveCount(0);
  const proposals = recordWrites(page, "/reply-proposals");

  await manual.getByRole("textbox", { name: "Reply to the customer" }).fill(STAFF_TEXT);
  await expectNoAccessibilityViolations(page);
  await submit.click();

  await expectAwaitingApproval(page);
  expect(proposals).toEqual([{ basis: "no_ai_draft", body: STAFF_TEXT }]);
});

test("UI-41: a manager sends a reply proposal as is in 1 action (TEST-27)", async ({ page }) => {
  await openTicket(page, AUTHORITY_REQUIRED_PATH, managerOnProposal);
  const reply = page.getByRole("main").getByRole("region", { name: "Reply for approval" });
  await expect(reply.getByRole("region", { name: "Staff proposal" })).toContainText("Mai Nguyen");
  await expect(reply.getByRole("region", { name: "AI draft for comparison" })).toBeVisible();
  await expectNoAccessibilityViolations(page);
  const actions = countActions();

  const confirmation = await openConfirmation(page, actions);
  await expectNoAccessibilityViolations(page);
  const body = await confirmSend(confirmation);

  expect(actions.count()).toBe(1);
  expect(body).toEqual({ basis: "reply_proposal", body: PROPOSAL_TEXT, proposal_id: PROPOSAL_ID });
  await expectReplySent(page);
});

test("UI-41: a manager edits and sends a reply proposal in 2 actions", async ({ page }) => {
  await openTicket(page, AUTHORITY_REQUIRED_PATH, managerOnProposal);
  const main = page.getByRole("main");
  const actions = countActions();

  await actions.click(main.getByRole("button", { name: "Edit proposal" }));
  const editor = main
    .getByRole("region", { name: "Staff proposal" })
    .getByRole("textbox", { name: "Reply to the customer" });
  await expect(editor).toHaveValue(PROPOSAL_TEXT);
  await expectNoAccessibilityViolations(page);
  await editor.fill(MANAGER_TEXT);
  const body = await sendAndConfirm(page, actions);

  expect(actions.count()).toBe(2);
  expect(body).toEqual({ basis: "reply_proposal", body: MANAGER_TEXT, proposal_id: PROPOSAL_ID });
  await expectReplySent(page);
});

test("staff read a ticket that awaits approval with every action disabled", async ({ page }) => {
  await openTicket(page, AUTHORITY_REQUIRED_PATH, { ticket: "example=read-only-for-staff" });

  const reply = page.getByRole("main").getByRole("region", { name: "Reply for approval" });

  await expect(reply).toContainText(READ_ONLY_LINE);
  await expect(reply).toContainText("Waiting for a manager");
  await expect(reply.getByRole("button", { name: "Edit proposal" })).toBeDisabled();
  await expect(reply.getByRole("button", { name: "Reject draft" })).toBeDisabled();
  await expect(reply.getByRole("button", { name: "Escalate ticket" })).toBeDisabled();
  await expect(reply.getByRole("button", { name: "More actions" })).toBeDisabled();
  await expect(reply.getByRole("button", { name: "Send reply" })).toBeDisabled();
  await expect(reply.getByRole("textbox")).toHaveCount(0);
  await expectNoAccessibilityViolations(page);
});

test("Escalate ticket asks for a reason, then escalates with it and the suggestion", async ({
  page,
}) => {
  await openTicket(page, DRAFT_READY_PATH, {
    ticket: "example=draft-ready",
    write: { request: createEscalationRequest, prefer: "example=escalated" },
  });
  await showEscalatedToStaff(page);
  const escalations = recordWrites(page, "/escalations");
  await page.getByRole("main").getByRole("button", { name: "Escalate ticket" }).click();
  const dialog = page.getByRole("dialog", { name: "Escalate ticket TCK-1042 to a manager?" });
  const escalate = dialog.getByRole("button", { name: "Escalate ticket", exact: true });

  await escalate.click();
  await expect(dialog.getByRole("alert")).toHaveText("Choose at least one reason.");
  expect(escalations).toEqual([]);
  await expectNoAccessibilityViolations(page);
  await dialog.getByRole("button", { name: "Missing case info" }).click();
  await escalate.click();

  await expect(dialog).toBeHidden();
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { name: "Escalated by Mai Nguyen" })).toBeFocused();
  expect(escalations).toEqual([
    { staff_reason_codes: ["missing_case_info"], suggestion_id: DRAFT_READY_SUGGESTION_ID },
  ]);
  await expect(main).toContainText(READ_ONLY_LINE);
  await expectNoAccessibilityViolations(page);
});

test("TEST-27: a manager replies to an escalated ticket under its reason and note", async ({
  page,
}) => {
  await openTicket(page, ESCALATED_PATH, {
    session: "example=manager",
    queue: "example=escalated",
    ticket: "example=escalated",
    write: {
      request: sendReplyRequest,
      prefer: "example=without-ai-draft",
      ticketAfter: "example=closed",
    },
  });
  const escalation = page
    .getByRole("main")
    .getByRole("region", { name: "Escalated by Mai Nguyen" });
  const note = escalation.getByText(ESCALATION_NOTE);
  const editor = escalation.getByRole("textbox", { name: "Reply to the customer" });
  await expect(escalation.getByText("Other", { exact: true })).toBeVisible();
  await expect(note).toBeVisible();
  expect(await getTop(note)).toBeLessThan(await getTop(editor));
  await expectNoAccessibilityViolations(page);

  await editor.fill(MANAGER_TEXT);
  const body = await sendAndConfirm(page);

  expect(body).toEqual({
    basis: "no_ai_draft",
    body: MANAGER_TEXT,
    suggestion_id: ESCALATED_SUGGESTION_ID,
  });
  await expectReplySent(page);
});
