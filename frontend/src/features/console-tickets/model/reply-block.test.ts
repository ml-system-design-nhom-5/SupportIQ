import { describe, expect, it } from "vitest";

import { MESSAGE_MAX_LENGTH } from "@/features/backend-requests";
import {
  findActionNote,
  findReplyBlock,
  getPrimaryAction,
} from "@/features/console-tickets/model/reply-block";
import {
  acknowledgeWarning,
  type ComposerState,
  createComposerState,
  rejectDraft,
} from "@/features/console-tickets/model/reply-composer";
import { STAFF_NOTE_MAX_LENGTH } from "@/features/console-tickets/model/staff-reason-codes";
import { DRAFT_READY_SUGGESTION_ID, readComposerTicket } from "@/test/console-screen";

const draftReady = readComposerTicket("draft-ready");
const manual = readComposerTicket("manual-mode");
const opened = createComposerState(DRAFT_READY_SUGGESTION_ID);
const acknowledged = acknowledgeWarning(opened, { warningId: "w1", isAcknowledged: true });
const rejected = { ...rejectDraft(opened), body: "My own reply." };
const withOther = { ...rejected, reasonCodes: new Set(["other"] as const) };
const authority = readComposerTicket("authority-required");
const authorityOpened = createComposerState(authority.suggestionId);

describe("findReplyBlock of the ticket", () => {
  it.each([
    ["closed", "This ticket is closed. A reply was already sent."],
    ["suggestion-pending", "The AI is still working on this ticket."],
    ["abstained-low-confidence", "Choose an intent to get a draft."],
    ["read-only-for-staff", "This ticket is read-only for you. A manager sends the reply."],
  ])("disables Send reply on the %s example", (name, reason) => {
    expect(findReplyBlock(readComposerTicket(name), acknowledged)).toBe(reason);
  });

  it("disables Send reply while an intent correction or Try AI again is sending", () => {
    expect(
      findReplyBlock(
        readComposerTicket("draft-ready", { isSuggestionRequested: true }),
        acknowledged,
      ),
    ).toBe("The AI is still working on this ticket.");
  });
});

describe("findReplyBlock of the warnings (UI-18)", () => {
  it.each([
    [draftReady, "Acknowledge 1 warning to send the reply."],
    [{ ...draftReady, warningIds: ["w1", "w2"] }, "Acknowledge 2 warnings to send the reply."],
  ])("counts the warnings left to acknowledge", (ticket, reason) => {
    expect(findReplyBlock(ticket, opened)).toBe(reason);
  });

  it("enables Send reply once every warning is acknowledged", () => {
    expect(findReplyBlock(draftReady, acknowledged)).toBeUndefined();
  });

  it("asks for no acknowledgement after a rejection", () => {
    expect(
      findReplyBlock(draftReady, { ...rejected, reasonCodes: new Set(["kb_gap"]) }),
    ).toBeUndefined();
  });
});

describe("findReplyBlock of a rejection (ADR-0006)", () => {
  it.each([
    [{ ...rejected }, "Choose why you rejected the draft to send the reply."],
    [{ ...withOther, note: " " }, "Write a note for the reason Other to send the reply."],
    [
      { ...withOther, note: "n".repeat(STAFF_NOTE_MAX_LENGTH + 1) },
      "Shorten the note to 1,000 characters to send the reply.",
    ],
  ])("says what the rejection needs", (state, reason) => {
    expect(findReplyBlock(draftReady, state)).toBe(reason);
  });

  it("enables Send reply with a note of exactly 1 000 characters", () => {
    expect(
      findReplyBlock(draftReady, { ...withOther, note: "n".repeat(STAFF_NOTE_MAX_LENGTH) }),
    ).toBeUndefined();
  });
});

describe("findReplyBlock of the text (UI-43)", () => {
  it.each([
    ["", "Write a reply to send it or to submit it for approval."],
    ["  \n", "Write a reply to send it or to submit it for approval."],
    ["a".repeat(MESSAGE_MAX_LENGTH + 1), "Shorten the reply to 2,000 characters to send it."],
    ["We sent the label to [EMAIL].", "Replace the highlighted text to send the reply."],
    ["You wrote [LITERAL_1].", "Replace the highlighted text to send the reply."],
  ])("disables Send reply for %j", (body, reason) => {
    expect(findReplyBlock(manual, { ...createComposerState(undefined), body })).toBe(reason);
  });

  it("enables Send reply for exactly 2 000 characters without a placeholder", () => {
    expect(
      findReplyBlock(manual, {
        ...createComposerState(undefined),
        body: "a".repeat(MESSAGE_MAX_LENGTH),
      }),
    ).toBeUndefined();
  });

  it("disables Send reply for a ready draft with a placeholder, sent as is", () => {
    const draft = {
      kind: "ai_draft",
      suggestionId: DRAFT_READY_SUGGESTION_ID,
      text: "We wrote to [EMAIL].",
    } as const;

    expect(findReplyBlock({ ...draftReady, draft }, acknowledged)).toBe(
      "Replace the highlighted text to send the reply.",
    );
  });
});

describe("getPrimaryAction (UI-16)", () => {
  it.each([
    ["draft-ready", "send_reply"],
    ["manual-mode", "send_reply"],
    ["authority-required", "submit_reply_proposal"],
    ["read-only-for-staff", "submit_reply_proposal"],
  ])("makes the main action of the %s example %s for staff", (name, action) => {
    expect(getPrimaryAction(readComposerTicket(name))).toBe(action);
  });

  it("makes Send reply the main action of a manager, also when authority is required", () => {
    expect(getPrimaryAction(readComposerTicket("awaiting-approval", { isManager: true }))).toBe(
      "send_reply",
    );
  });

  it("keeps Submit for approval in place while the AI works on a ticket that requires authority", () => {
    const pending = { ...readComposerTicket("authority-required"), allowedActions: new Set([]) };

    expect(getPrimaryAction(pending)).toBe("submit_reply_proposal");
  });
});

describe("findReplyBlock of a manager", () => {
  it("says that the AI works, not that the ticket is read-only, on an escalated ticket", () => {
    const ticket = {
      ...readComposerTicket("escalated", { isManager: true }),
      isSuggestionRunning: true,
    };

    expect(findReplyBlock(ticket, createComposerState(ticket.suggestionId))).toBe(
      "The AI is still working on this ticket.",
    );
  });

  it("says that only staff submit a reply for approval", () => {
    const ticket = readComposerTicket("awaiting-approval", { isManager: true });

    expect(
      findReplyBlock(ticket, createComposerState(ticket.suggestionId), "submit_reply_proposal"),
    ).toBe("Only staff submit a reply for approval.");
  });
});

describe("findActionNote of Escalate ticket (UI-16)", () => {
  it("says why a manager cannot escalate once the reply can be sent", () => {
    const ticket = readComposerTicket("escalated", { isManager: true });
    const written = { ...createComposerState(ticket.suggestionId), body: "We call you today." };

    expect(findReplyBlock(ticket, written)).toBeUndefined();
    expect(findActionNote(ticket)).toBe(
      "Only staff escalate a ticket. Managers handle escalated tickets.",
    );
  });

  it("names Submit for approval too for a manager in manual handling, where it is a button", () => {
    const ticket = {
      ...readComposerTicket("manual-mode", { isManager: true }),
      allowedActions: new Set(["send_reply"] as const),
    };
    const written = { ...createComposerState(ticket.suggestionId), body: "We call you today." };

    expect(ticket.situation).toBe("manual_handling");
    expect(findReplyBlock(ticket, written)).toBeUndefined();
    expect(findActionNote(ticket)).toBe(
      "Only staff escalate a ticket or submit a reply for approval.",
    );
  });

  it("keeps the note of a proposal, which names Escalate ticket too", () => {
    expect(findActionNote(readComposerTicket("awaiting-approval", { isManager: true }))).toBe(
      "Reject draft and Escalate ticket are not available while the ticket awaits approval.",
    );
  });

  it("notes nothing for staff, who may escalate", () => {
    expect(findActionNote(draftReady)).toBeUndefined();
  });
});

describe("findReplyBlock while a write hands the ticket to a manager", () => {
  it.each([
    ["submit_reply_proposal", "The reply is being submitted for approval."],
    ["escalate", "The ticket is being escalated."],
  ] as const)("disables the actions while %s is sending", (handover, reason) => {
    expect(findReplyBlock({ ...draftReady, handover }, acknowledged, "send_reply")).toBe(reason);
  });
});

describe("findReplyBlock of Submit for approval", () => {
  it("is enabled on a ticket that requires authority, with the note of the bar", () => {
    const state = acknowledgeAll(authority.warningIds, authorityOpened);

    expect(findReplyBlock(authority, state)).toBeUndefined();
    expect(findActionNote(authority)).toBe("A manager sends the reply on this ticket.");
  });

  it("says what a rejection still needs, with the verb of the action", () => {
    expect(findReplyBlock(authority, { ...rejectDraft(authorityOpened), body: "Mine." })).toBe(
      "Choose why you rejected the draft to submit the reply.",
    );
  });

  it("asks for text to submit after a rejection with a reason", () => {
    const rejectedWithReason = {
      ...rejectDraft(authorityOpened),
      reasonCodes: new Set(["kb_gap"] as const),
    };

    expect(findReplyBlock(authority, rejectedWithReason)).toBe(
      "Write a reply to submit it for approval.",
    );
  });
});

describe("findReplyBlock of Submit for approval, the checks it shares with Send reply", () => {
  it("asks to acknowledge the warnings, as Send reply does, wherever it sits", () => {
    expect(findReplyBlock(draftReady, opened, "submit_reply_proposal")).toBe(
      "Acknowledge 1 warning to submit the reply.",
    );
  });

  it("is disabled for a ready draft with a placeholder, sent as is", () => {
    const draft = {
      kind: "ai_draft",
      suggestionId: DRAFT_READY_SUGGESTION_ID,
      text: "We wrote to [EMAIL].",
    } as const;

    expect(findReplyBlock({ ...authority, draft }, authorityOpened)).toBe(
      "Replace the highlighted text to submit the reply.",
    );
  });

  it("is disabled while the AI runs, as backend refuses a proposal then", () => {
    expect(
      findReplyBlock(
        readComposerTicket("draft-ready", { isSuggestionRequested: true }),
        acknowledged,
        "submit_reply_proposal",
      ),
    ).toBe("The AI is still working on this ticket.");
  });
});

describe("findReplyBlock of the other states", () => {
  it("asks to write or escalate when the AI recommends an escalation", () => {
    const ticket = {
      ...readComposerTicket("manual-mode"),
      situation: "escalation_recommended",
    } as const;

    expect(findReplyBlock(ticket, createComposerState(undefined))).toBe(
      "Write a reply to send it, or escalate the ticket.",
    );
  });

  it("asks a manager to write on an escalated ticket", () => {
    expect(findReplyBlock(readComposerTicket("escalated"), createComposerState(undefined))).toBe(
      "Write a reply to send it.",
    );
  });

  it("enables Send reply of a proposal as is, with the note of the bar", () => {
    const ticket = readComposerTicket("awaiting-approval", { isManager: true });

    expect(findReplyBlock(ticket, createComposerState(ticket.suggestionId))).toBeUndefined();
    expect(findActionNote(ticket)).toBe(
      "Reject draft and Escalate ticket are not available while the ticket awaits approval.",
    );
  });
});

/**
 * Acknowledge every warning of a ticket.
 *
 * @param warningIds - The warnings.
 * @param state - The state to start from.
 * @returns The state with every warning acknowledged.
 */
function acknowledgeAll(warningIds: readonly string[], state: ComposerState): ComposerState {
  return warningIds.reduce(
    (current, warningId) => acknowledgeWarning(current, { warningId, isAcknowledged: true }),
    state,
  );
}
