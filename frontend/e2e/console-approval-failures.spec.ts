/**
 * The main failure of Submit for approval against the Prism mock (console UI design, Flow and
 * Errors and guardrails; TEST-01): the connection is lost, so nobody knows whether the proposal
 * arrived (ERR-16). The reply area says so, keeps the text, and sends nothing on its own after
 * that; staff submit the same reply again with the same `Idempotency-Key`, so a manager gets it
 * once (TS-29). `createReplyProposal` is a write with a key, so the app retries it automatically
 * with that key before it gives up (ERR-13); the lost connection loses those retries too.
 */
import { expect, test } from "@playwright/test";

import {
  createProposalRequest,
  expectAwaitingApproval,
  idempotencyKeyPattern,
  loseWrite,
  MANUAL_MODE_PATH,
  manualProposalFlow,
  openTicket,
  recordWrites,
  RETRY_WAIT,
} from "./support/console-flows.ts";
import { expectNoAccessibilityViolations } from "./support/page-checks.ts";

/** The text that staff write themselves. */
const STAFF_TEXT = "A manager decides on your request. We will write to you again then.";
/** The banner of a submission whose outcome is unknown, such as after a lost connection. */
const UNKNOWN_SUBMISSION_BANNER =
  "The reply may have been submitted. We could not confirm it. Submitting the same reply again is safe: a manager gets it once.";

test("TS-29: a lost Submit for approval keeps the text, is not sent again, and reuses its key", async ({
  page,
}) => {
  await page.clock.install();
  await openTicket(page, MANUAL_MODE_PATH, manualProposalFlow);
  const manual = page.getByRole("main").getByRole("region", { name: "Manual handling" });
  const editor = manual.getByRole("textbox", { name: "Reply to the customer" });
  const submit = manual.getByRole("button", { name: "Submit for approval" });
  await editor.fill(STAFF_TEXT);
  const lostProposal = await loseWrite(page, createProposalRequest);
  const proposals = recordWrites(page, "/reply-proposals");

  await submit.click();

  await expect(page.getByRole("alert")).toHaveText(UNKNOWN_SUBMISSION_BANNER);
  await expect(editor).toHaveValue(STAFF_TEXT);
  // The banner shows once the automatic retries gave up, so no request may follow it.
  const lostAttempts = lostProposal.keys.length;
  await page.clock.fastForward(RETRY_WAIT);
  expect(lostProposal.keys).toHaveLength(lostAttempts);
  await expectNoAccessibilityViolations(page);
  lostProposal.restore();

  await submit.click();

  await expectAwaitingApproval(page);
  expect(lostProposal.keys).toHaveLength(lostAttempts + 1);
  expect([...new Set(lostProposal.keys)]).toEqual([expect.stringMatching(idempotencyKeyPattern)]);
  expect(proposals.at(-1)).toEqual({ basis: "no_ai_draft", body: STAFF_TEXT });
});
