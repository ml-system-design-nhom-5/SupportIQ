/**
 * Helpers of the console flows against the Prism mock (console UI design, Flow and Action counts):
 * count the deliberate actions of a flow (UI-41), record the bodies of its writes, choose the next
 * answer of the ticket when a write goes out, and send a reply through its confirmation (UI-17).
 * The mock is stateless and answers with the example files, and the console loads the ticket again
 * as soon as a write succeeds, so a flow chooses that answer before the mock answers the write.
 */
import { expect, type Locator, type Page } from "@playwright/test";

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

/**
 * Choose the next answer of the ticket when a write goes out, before the mock answers the write.
 *
 * @param page - The page.
 * @param writeUrl - The URL glob of the write.
 * @param change - The setter of the ticket's `Prefer` value, and the value after the write.
 */
export async function changeTicketOnWrite(
  page: Page,
  writeUrl: string,
  change: TicketChange,
): Promise<void> {
  await page.route(writeUrl, async (route) => {
    change.chooseTicket(change.prefer);
    await route.fallback();
  });
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
