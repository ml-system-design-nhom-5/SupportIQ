/**
 * Helpers of the console flows against the Prism mock (console UI design, Flow and Action counts):
 * open a ticket with the examples of a flow, count the deliberate actions of a flow (UI-41), record
 * the bodies of its writes, choose the next answer of the ticket when a write goes out, lose the
 * connection for a write, send a reply through its confirmation (UI-17), and check the ticket after
 * Submit for approval. The mock is stateless
 * and answers with the example files, and the console loads the ticket again as soon as a write
 * succeeds, so a flow chooses that answer before the mock answers the write.
 */
import { expect, type Locator, type Page } from "@playwright/test";

import { type MockedRequest, preferOutcome } from "./mock-outcomes.ts";
import { createSessionCookie } from "./sign-in.ts";

const getSessionRequest: MockedRequest = { method: "GET", path: "/v1/sessions/current" };
const listTicketsRequest: MockedRequest = { method: "GET", path: "/v1/console/tickets" };
const getTicketRequest: MockedRequest = { method: "GET", path: "/v1/console/tickets/*" };
export const sendReplyRequest: MockedRequest = {
  method: "POST",
  path: "/v1/console/tickets/*/replies",
};
export const createProposalRequest: MockedRequest = {
  method: "POST",
  path: "/v1/console/tickets/*/reply-proposals",
};

/** The paths of the tickets of the draft-ready and manual-mode examples. */
export const DRAFT_READY_PATH = "/console/tickets/TCK-1042";
export const MANUAL_MODE_PATH = "/console/tickets/TCK-1050";

/** The current suggestion of the draft-ready example. */
export const DRAFT_READY_SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";
/** The canonical `text` of the ready drafts of the examples, which Send reply sends as is. */
export const DRAFT_TEXT =
  "Hello Lan Tran, thank you for your patience.\n\nYour refund request for order ORD-20931 is under review. This sample sentence stands for a policy statement from the cited document.";
/** An `Idempotency-Key`: a UUID, as the contract requires. */
export const idempotencyKeyPattern = /^[0-9a-f-]{36}$/;
/** The line above the buttons when a ticket is read-only for staff. */
export const READ_ONLY_LINE = "This ticket is read-only for you. A manager sends the reply.";
/**
 * How far the clock of the page jumps after a failed write: far beyond the delay of an automatic
 * retry (ERR-13), so a retry would go out. The clock is fake, so no test waits in real time
 * (TEST-14).
 */
export const RETRY_WAIT = "01:00";

/** A write of a flow, its example, and the `Prefer` value of the ticket after it. */
export type FlowWrite = {
  readonly request: MockedRequest;
  readonly prefer: string;
  /** Absent when the flow answers the later loads of the ticket itself. */
  readonly ticketAfter?: string;
};

/** The examples that a flow starts with, as `Prefer` values. */
export type FlowExamples = {
  /** The session; `example=staff` by default. */
  readonly session?: string;
  /** The queue of the inbox; `example=open-queue` by default. */
  readonly queue?: string;
  readonly ticket: string;
  /** The writes of the flow; none when the flow only reads. */
  readonly writes?: readonly FlowWrite[];
};

/** The manual-mode ticket, whose reply staff write and submit for approval without a draft. */
export const manualProposalFlow: FlowExamples = {
  ticket: "example=manual-mode",
  writes: [
    {
      request: createProposalRequest,
      prefer: "example=without-ai-draft",
      ticketAfter: "example=read-only-for-staff",
    },
  ],
};

/**
 * The next answer of the ticket after a write: the function that chooses the `Prefer` value of the
 * later loads of the ticket, as `preferOutcome` returns it, and the value after the write, such as
 * `example=closed`.
 */
export type TicketChange = {
  readonly chooseTicket: (prefer: string) => void;
  readonly prefer: string;
};

/** The deliberate actions of a flow (UI-41). */
export type ActionCounter = {
  /** Clicks the target and counts one action. */
  readonly click: (target: Locator) => Promise<void>;
  /** The number of actions so far. */
  readonly count: () => number;
};

/** An open confirmation of Send reply, and the bodies of `sendReply` sent since it opened. */
export type OpenConfirmation = {
  readonly dialog: Locator;
  readonly sentBodies: readonly unknown[];
};

/** A write whose connection is lost until the flow brings it back. */
export type LostWrite = {
  /** The `Idempotency-Key` of every request of the write, lost or not, in order. */
  readonly keys: readonly (string | undefined)[];
  /** Brings the connection back: the later requests reach the mock. */
  readonly restore: () => void;
};

/**
 * Sign in, choose the examples of the flow, and open the ticket.
 *
 * @param page - The page.
 * @param ticketPath - The path of the ticket.
 * @param examples - The `Prefer` values of the session, the queue, the ticket, and the writes.
 * @returns A function that chooses the `Prefer` value of the later loads of the ticket.
 */
export async function openTicket(
  page: Page,
  ticketPath: string,
  examples: FlowExamples,
): Promise<(prefer: string) => void> {
  await preferOutcome(page, getSessionRequest, examples.session ?? "example=staff");
  await preferOutcome(page, listTicketsRequest, examples.queue ?? "example=open-queue");
  const chooseTicket = await preferOutcome(page, getTicketRequest, examples.ticket);
  await Promise.all((examples.writes ?? []).map((write) => answerWrite(page, write, chooseTicket)));
  await createSessionCookie(page);
  await page.goto(ticketPath);
  return chooseTicket;
}

/**
 * Choose the example of a write, and the next answer of the ticket when the write goes out.
 *
 * @param page - The page.
 * @param write - The write, its example, and the `Prefer` value of the ticket after it.
 * @param chooseTicket - The setter of the ticket's `Prefer` value.
 */
async function answerWrite(
  page: Page,
  write: FlowWrite,
  chooseTicket: (prefer: string) => void,
): Promise<void> {
  await preferOutcome(page, write.request, write.prefer);
  if (write.ticketAfter !== undefined) {
    await changeTicketOnWrite(page, write.request, { chooseTicket, prefer: write.ticketAfter });
  }
}

/**
 * Choose the next answer of the ticket when a write goes out, before the mock answers the write.
 *
 * @param page - The page.
 * @param write - The method and the path of the write.
 * @param change - The setter of the ticket's `Prefer` value, and the value after the write.
 */
export async function changeTicketOnWrite(
  page: Page,
  write: MockedRequest,
  change: TicketChange,
): Promise<void> {
  await page.route(`**${write.path}`, async (route) => {
    change.chooseTicket(change.prefer);
    await route.fallback();
  });
}

/**
 * Lose the connection for every request of a write until the flow brings it back, as when the
 * network drops: the first attempt of a staff action fails, and so does any automatic retry of it.
 * No response reaches the page, so the outcome is unknown (ERR-16).
 *
 * @param page - The page.
 * @param write - The method and the path of the write.
 * @returns The keys of the requests of the write, and the function that brings the connection
 *   back.
 */
export async function loseWrite(page: Page, write: MockedRequest): Promise<LostWrite> {
  const keys: (string | undefined)[] = [];
  let isLost = true;
  await page.route(`**${write.path}`, async (route) => {
    keys.push(route.request().headers()["idempotency-key"]);
    await (isLost ? route.abort("failed") : route.fallback());
  });
  return {
    keys,
    restore: () => {
      isLost = false;
    },
  };
}

/**
 * Record the parsed body of every `POST` whose path ends as given.
 *
 * @param page - The page.
 * @param pathEnd - The end of the path, such as `/replies`.
 * @returns The bodies, in the order in which the requests go out.
 */
export function recordWrites(page: Page, pathEnd: string): readonly unknown[] {
  const bodies: unknown[] = [];
  page.on("request", (request) => {
    if (request.method() === "POST" && new URL(request.url()).pathname.endsWith(pathEnd)) {
      bodies.push(request.postDataJSON());
    }
  });
  return bodies;
}

/**
 * Count the deliberate actions of a flow. Typing, acknowledging a warning (UI-18), and confirming
 * Send reply (UI-17) go around the counter, because UI-41 does not count them.
 *
 * @returns The counter, at zero.
 */
export function countActions(): ActionCounter {
  let count = 0;
  return {
    click: async (target) => {
      await target.click();
      count += 1;
    },
    count: () => count,
  };
}

/**
 * Open the confirmation with Send reply, which counts as an action, and check that nothing is
 * sent yet (UI-17). Every example of a ticket has the customer Lan Tran.
 *
 * @param page - The page.
 * @param actions - The counter of the flow.
 * @returns The confirmation, and the bodies of `sendReply` from now on.
 */
export async function openConfirmation(
  page: Page,
  actions: ActionCounter,
): Promise<OpenConfirmation> {
  const sentBodies = recordWrites(page, "/replies");
  await actions.click(page.getByRole("main").getByRole("button", { name: "Send reply" }));
  const dialog = page.getByRole("alertdialog", { name: "Send this reply to Lan Tran?" });
  await expect(dialog).toContainText("A sent reply cannot be changed.");
  expect(sentBodies).toEqual([]);
  return { dialog, sentBodies };
}

/**
 * Confirm Send reply, which is not counted as an action (UI-41).
 *
 * @param confirmation - The open confirmation.
 * @returns The parsed body of the one `sendReply` request.
 */
export async function confirmSend({ dialog, sentBodies }: OpenConfirmation): Promise<unknown> {
  await dialog.getByRole("button", { name: "Send reply" }).click();
  await expect.poll(() => sentBodies.length).toBe(1);
  return sentBodies[0];
}

/**
 * Send the reply: Send reply, then the Send reply of the confirmation.
 *
 * @param page - The page.
 * @param actions - The counter of the flow; a new one by default.
 * @returns The parsed body of the one `sendReply` request.
 */
export async function sendAndConfirm(page: Page, actions = countActions()): Promise<unknown> {
  return confirmSend(await openConfirmation(page, actions));
}

/**
 * Check that the ticket, loaded again after the send, shows the sent reply (console UI design,
 * States: Closed).
 *
 * @param page - The page.
 */
export async function expectReplySent(page: Page): Promise<void> {
  await expect(page.getByRole("main").getByRole("region", { name: "Reply sent" })).toBeVisible();
}

/**
 * Check that the ticket, loaded again after Submit for approval, awaits approval and is read-only
 * for staff, with the focus on the heading of the reply area (console UI design, Flow; UI-30).
 *
 * @param page - The page.
 */
export async function expectAwaitingApproval(page: Page): Promise<void> {
  const main = page.getByRole("main");
  await expect(main.getByRole("heading", { name: "Reply for approval" })).toBeFocused();
  const reply = main.getByRole("region", { name: "Reply for approval" });
  await expect(reply).toContainText(READ_ONLY_LINE);
  await expect(reply.getByRole("textbox")).toHaveCount(0);
}
