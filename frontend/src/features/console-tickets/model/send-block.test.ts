import { describe, expect, it } from "vitest";

import { MESSAGE_MAX_LENGTH } from "@/features/backend-requests";
import {
  acknowledgeWarning,
  createComposerState,
  rejectDraft,
} from "@/features/console-tickets/model/reply-composer";
import { findSendBlock } from "@/features/console-tickets/model/send-block";
import { STAFF_NOTE_MAX_LENGTH } from "@/features/console-tickets/model/staff-reason-codes";
import { DRAFT_READY_SUGGESTION_ID, readComposerTicket } from "@/test/console-screen";

const draftReady = readComposerTicket("draft-ready");
const manual = readComposerTicket("manual-mode");
const opened = createComposerState(DRAFT_READY_SUGGESTION_ID);
const acknowledged = acknowledgeWarning(opened, { warningId: "w1", isAcknowledged: true });
const rejected = { ...rejectDraft(opened), body: "My own reply." };
const withOther = { ...rejected, reasonCodes: new Set(["other"] as const) };

describe("findSendBlock of the ticket", () => {
  it.each([
    ["closed", "This ticket is closed. A reply was already sent."],
    ["suggestion-pending", "The AI is still working on this ticket."],
    ["authority-required", "Only a manager can send the reply of this ticket."],
    ["abstained-low-confidence", "Choose an intent to get a draft."],
  ])("disables Send reply on the %s example", (name, reason) => {
    expect(findSendBlock(readComposerTicket(name), acknowledged)).toBe(reason);
  });

  it("disables Send reply while an intent correction or Try AI again is sending", () => {
    expect(findSendBlock(readComposerTicket("draft-ready", true), acknowledged)).toBe(
      "The AI is still working on this ticket.",
    );
  });
});

describe("findSendBlock of the warnings (UI-18)", () => {
  it.each([
    [draftReady, "Acknowledge 1 warning to send the reply."],
    [{ ...draftReady, warningIds: ["w1", "w2"] }, "Acknowledge 2 warnings to send the reply."],
  ])("counts the warnings left to acknowledge", (ticket, reason) => {
    expect(findSendBlock(ticket, opened)).toBe(reason);
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
    [{ ...withOther, note: " " }, "Write a note for the reason Other to send the reply."],
    [
      { ...withOther, note: "n".repeat(STAFF_NOTE_MAX_LENGTH + 1) },
      "Shorten the note to 1,000 characters to send the reply.",
    ],
  ])("says what the rejection needs", (state, reason) => {
    expect(findSendBlock(draftReady, state)).toBe(reason);
  });

  it("enables Send reply with a note of exactly 1 000 characters", () => {
    expect(
      findSendBlock(draftReady, { ...withOther, note: "n".repeat(STAFF_NOTE_MAX_LENGTH) }),
    ).toBeUndefined();
  });
});

describe("findSendBlock of the text (UI-43)", () => {
  it.each([
    ["", "Write a reply to send it."],
    ["  \n", "Write a reply to send it."],
    ["a".repeat(MESSAGE_MAX_LENGTH + 1), "Shorten the reply to 2,000 characters to send it."],
    ["We sent the label to [EMAIL].", "Replace the highlighted text to send the reply."],
    ["You wrote [LITERAL_1].", "Replace the highlighted text to send the reply."],
  ])("disables Send reply for %j", (body, reason) => {
    expect(findSendBlock(manual, { ...createComposerState(undefined), body })).toBe(reason);
  });

  it("enables Send reply for exactly 2 000 characters without a placeholder", () => {
    expect(
      findSendBlock(manual, {
        ...createComposerState(undefined),
        body: "a".repeat(MESSAGE_MAX_LENGTH),
      }),
    ).toBeUndefined();
  });

  it("disables Send reply for a ready draft with a placeholder, sent as is", () => {
    const draft = { suggestionId: DRAFT_READY_SUGGESTION_ID, text: "We wrote to [EMAIL]." };

    expect(findSendBlock({ ...draftReady, draft }, acknowledged)).toBe(
      "Replace the highlighted text to send the reply.",
    );
  });
});
