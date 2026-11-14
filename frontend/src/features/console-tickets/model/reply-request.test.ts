import { describe, expect, it } from "vitest";

import { canChangeDraft } from "@/features/console-tickets/model/composer-ticket";
import {
  acknowledgeWarning,
  createComposerState,
  followSuggestion,
  rejectDraft,
  startEditing,
} from "@/features/console-tickets/model/reply-composer";
import {
  buildReplyProposalRequest,
  buildSendReplyRequest,
} from "@/features/console-tickets/model/reply-request";
import { DRAFT_READY_SUGGESTION_ID, readComposerTicket } from "@/test/console-screen";

const draftReady = readComposerTicket("draft-ready");
const opened = createComposerState(DRAFT_READY_SUGGESTION_ID);
const acknowledged = acknowledgeWarning(opened, { warningId: "w1", isAcknowledged: true });

describe("toComposerTicket", () => {
  it("reads the ready draft, its suggestion, and its warnings", () => {
    expect(draftReady).toMatchObject({
      allowedActions: new Set([
        "send_reply",
        "submit_reply_proposal",
        "escalate",
        "correct_intent",
      ]),
      status: "open",
      isAuthorityRequired: false,
      isSuggestionRunning: false,
      suggestionId: DRAFT_READY_SUGGESTION_ID,
      draft: { kind: "ai_draft", suggestionId: DRAFT_READY_SUGGESTION_ID },
      warningIds: ["w1"],
    });
    expect(draftReady.draft?.text).toMatch(/^Hello Lan Tran, thank you for your patience\./);
  });

  it("has no suggestion and no draft in manual mode", () => {
    const manual = readComposerTicket("manual-mode");

    expect(manual).not.toHaveProperty("suggestionId");
    expect(manual).not.toHaveProperty("draft");
  });

  it("says that the AI is running while a part is pending", () => {
    expect(readComposerTicket("suggestion-pending")).toMatchObject({ isSuggestionRunning: true });
    expect(readComposerTicket("suggestion-pending")).not.toHaveProperty("draft");
  });

  it("says that the AI is running while a correction or Try AI again is sending", () => {
    expect(readComposerTicket("draft-ready", { isSuggestionRequested: true })).toMatchObject({
      isSuggestionRunning: true,
    });
  });

  it("says that a ticket is closed", () => {
    expect(readComposerTicket("closed")).toMatchObject({ status: "closed" });
  });
});

describe("buildSendReplyRequest of a ready draft", () => {
  it("sends the draft as is with the basis ai_draft and the acknowledged warning", () => {
    expect(buildSendReplyRequest(draftReady, acknowledged)).toEqual({
      basis: "ai_draft",
      body: draftReady.draft?.text,
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
      acknowledged_warning_ids: ["w1"],
    });
  });

  it("names only the warnings that staff acknowledged, so 422 stays the backstop (UI-18)", () => {
    expect(buildSendReplyRequest(draftReady, opened)).toMatchObject({
      acknowledged_warning_ids: [],
    });
  });

  it("never names an acknowledged ID that the current draft does not have", () => {
    const other = acknowledgeWarning(acknowledged, { warningId: "w9", isAcknowledged: true });

    expect(buildSendReplyRequest(draftReady, other)).toMatchObject({
      acknowledged_warning_ids: ["w1"],
    });
  });

  it("sends the edited text with the basis ai_draft", () => {
    expect(
      buildSendReplyRequest(draftReady, startEditing(acknowledged, "Edited reply.")),
    ).toMatchObject({ basis: "ai_draft", body: "Edited reply." });
  });
});

describe("buildSendReplyRequest of a text kept over a new draft", () => {
  it("sends the text kept over a new draft as an edit of the new draft", () => {
    const kept = followSuggestion(
      { ...rejectDraft(createComposerState("s0")), body: "Mine." },
      {
        suggestionId: DRAFT_READY_SUGGESTION_ID,
        proposalId: undefined,
      },
    );

    expect(buildSendReplyRequest(draftReady, kept)).toEqual({
      basis: "ai_draft",
      body: "Mine.",
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
      acknowledged_warning_ids: [],
    });
  });
});

describe("buildSendReplyRequest of a rejected draft", () => {
  it("sends the reason codes in the order of the contract, without a note", () => {
    expect(
      buildSendReplyRequest(draftReady, {
        ...rejectDraft(opened),
        body: "My own reply.",
        reasonCodes: new Set(["unsupported_claim", "wrong_intent"]),
      }),
    ).toEqual({
      basis: "rejected_ai_draft",
      body: "My own reply.",
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
      staff_reason_codes: ["wrong_intent", "unsupported_claim"],
    });
  });

  it("sends the note of the reason code other", () => {
    expect(
      buildSendReplyRequest(draftReady, {
        ...rejectDraft(opened),
        body: "My own reply.",
        reasonCodes: new Set(["other"]),
        note: "The customer called us.",
      }),
    ).toMatchObject({ staff_reason_codes: ["other"], note: "The customer called us." });
  });
});

describe("buildSendReplyRequest without a ready draft", () => {
  it("sends the basis no_ai_draft with the suggestion that staff saw", () => {
    expect(
      buildSendReplyRequest(readComposerTicket("abstained-low-confidence"), {
        ...opened,
        body: "My reply.",
      }),
    ).toEqual({
      basis: "no_ai_draft",
      body: "My reply.",
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
    });
  });

  it("sends the basis no_ai_draft without a suggestion in manual mode", () => {
    expect(
      buildSendReplyRequest(readComposerTicket("manual-mode"), {
        ...createComposerState(undefined),
        body: "Hi.",
      }),
    ).toEqual({ basis: "no_ai_draft", body: "Hi." });
  });
});

describe("canChangeDraft", () => {
  it.each([
    ["draft-ready", true],
    ["authority-required", true],
    ["abstained-low-confidence", false],
    ["read-only-for-staff", false],
  ])("answers for the %s example: %s", (name, canChange) => {
    expect(canChangeDraft(readComposerTicket(name))).toBe(canChange);
  });
});

describe("buildSendReplyRequest of a manager on a proposal (FR-06)", () => {
  const ticket = readComposerTicket("awaiting-approval");
  const proposalOpened = createComposerState(ticket.suggestionId);

  it("sends the proposal as is with the basis reply_proposal", () => {
    expect(buildSendReplyRequest(ticket, proposalOpened)).toEqual({
      basis: "reply_proposal",
      body: ticket.draft?.text,
      proposal_id: "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52",
    });
  });

  it("sends the edited proposal with the basis reply_proposal", () => {
    expect(
      buildSendReplyRequest(ticket, startEditing(proposalOpened, "The edited reply.")),
    ).toEqual({
      basis: "reply_proposal",
      body: "The edited reply.",
      proposal_id: "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52",
    });
  });
});

describe("buildReplyProposalRequest", () => {
  it("submits the draft with the basis that Send reply would use", () => {
    expect(buildReplyProposalRequest(draftReady, acknowledged)).toEqual(
      buildSendReplyRequest(draftReady, acknowledged),
    );
  });

  it("submits the text kept over a new draft as an edit of the new draft", () => {
    const kept = followSuggestion(startEditing(createComposerState("s0"), "Edited reply."), {
      suggestionId: DRAFT_READY_SUGGESTION_ID,
      proposalId: undefined,
    });

    expect(buildReplyProposalRequest(draftReady, kept)).toEqual({
      basis: "ai_draft",
      body: "Edited reply.",
      suggestion_id: DRAFT_READY_SUGGESTION_ID,
      acknowledged_warning_ids: [],
    });
  });

  it("submits a reply without a draft in manual mode", () => {
    expect(
      buildReplyProposalRequest(readComposerTicket("manual-mode"), {
        ...createComposerState(undefined),
        body: "Here is the return label.",
      }),
    ).toEqual({ basis: "no_ai_draft", body: "Here is the return label." });
  });
});
