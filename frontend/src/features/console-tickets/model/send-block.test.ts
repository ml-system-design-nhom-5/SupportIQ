import { describe, expect, it } from "vitest";

import { initialComposerState, rejectDraft } from "@/features/console-tickets/model/reply-composer";
import {
  type ComposerTicket,
  findSendBlock,
  toComposerTicket,
} from "@/features/console-tickets/model/reply-request";
import { toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { buildWorkspaceRegions } from "@/features/console-tickets/model/workspace-regions";
import { readOperationExample } from "@/test/contract-examples";

/**
 * Read the composer ticket of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns What the composer reads of it.
 */
function readTicket(name: string): ComposerTicket {
  const workspace = toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name));
  return toComposerTicket(workspace, buildWorkspaceRegions(workspace));
}

const draftReady = readTicket("draft-ready");
const acknowledged = { ...initialComposerState, acknowledgedWarningIds: new Set(["w1"]) };
const rejected = { ...rejectDraft(initialComposerState), body: "My own reply." };

describe("findSendBlock of the ticket", () => {
  it.each([
    ["suggestion-pending", "The AI is still working on this ticket."],
    ["authority-required", "Only a manager can send the reply of this ticket."],
    ["closed", "You cannot send a reply on this ticket."],
    ["abstained-low-confidence", "Choose an intent to get a draft."],
  ])("disables Send reply on the %s example", (name, reason) => {
    expect(findSendBlock(readTicket(name), acknowledged)).toBe(reason);
  });
});

describe("findSendBlock of the warnings (UI-18)", () => {
  it.each([
    [draftReady, "Acknowledge 1 warning to send the reply."],
    [{ ...draftReady, warningIds: ["w1", "w2"] }, "Acknowledge 2 warnings to send the reply."],
  ])("counts the warnings left to acknowledge", (ticket, reason) => {
    expect(findSendBlock(ticket, initialComposerState)).toBe(reason);
  });

  it("enables Send reply once every warning is acknowledged", () => {
    expect(findSendBlock(draftReady, acknowledged)).toBeUndefined();
  });

  it("asks for no acknowledgement after a rejection", () => {
    expect(
      findSendBlock(draftReady, { ...rejected, reasonCodes: new Set(["kb_gap"]) }),
    ).toBeUndefined();
  });
});

describe("findSendBlock of a rejection (ADR-0006)", () => {
  it.each([
    [{ ...rejected }, "Choose why you rejected the draft to send the reply."],
    [
      { ...rejected, reasonCodes: new Set(["other"] as const), note: " " },
      "Write a note for the reason Other to send the reply.",
    ],
    [
      { ...rejected, reasonCodes: new Set(["other"] as const), note: "n".repeat(1001) },
      "Shorten the note to 1,000 characters to send the reply.",
    ],
  ])("says what the rejection needs", (state, reason) => {
    expect(findSendBlock(draftReady, state)).toBe(reason);
  });
});

describe("findSendBlock of the text (UI-43)", () => {
  it.each([
    ["", "Write a reply to send it."],
    ["  \n", "Write a reply to send it."],
    ["a".repeat(2001), "Shorten the reply to 2,000 characters to send it."],
    ["We sent the label to [EMAIL].", "Replace the highlighted text to send the reply."],
    ["You wrote [LITERAL_1].", "Replace the highlighted text to send the reply."],
  ])("disables Send reply for %j", (body, reason) => {
    expect(findSendBlock(readTicket("manual-mode"), { ...initialComposerState, body })).toBe(
      reason,
    );
  });

  it("enables Send reply for 2 000 characters without a placeholder", () => {
    expect(
      findSendBlock(readTicket("manual-mode"), { ...initialComposerState, body: "a".repeat(2000) }),
    ).toBeUndefined();
  });
});
