import { describe, expect, it } from "vitest";

import {
  acknowledgeWarning,
  createComposerState,
  followSuggestion,
  rejectDraft,
  startEditing,
} from "@/features/console-tickets/model/reply-composer";
import {
  buildSendReplyRequest,
  canChangeDraft,
  isSameReply,
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
      isAuthorityRequired: false,
      isClosed: false,
      isSuggestionRunning: false,
      suggestionId: DRAFT_READY_SUGGESTION_ID,
      draft: { suggestionId: DRAFT_READY_SUGGESTION_ID },
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
    expect(readComposerTicket("draft-ready", true)).toMatchObject({ isSuggestionRunning: true });
  });

  it("says that a ticket is closed", () => {
    expect(readComposerTicket("closed")).toMatchObject({ isClosed: true });
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

  it("sends the text kept over a new draft as an edit of the new draft", () => {
    const kept = followSuggestion(
      { ...rejectDraft(createComposerState("s0")), body: "Mine." },
      DRAFT_READY_SUGGESTION_ID,
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

describe("isSameReply", () => {
  const rejected = { ...rejectDraft(opened), body: "My own reply." };

  it("matches the same reply confirmed again", () => {
    expect(
      isSameReply(
        buildSendReplyRequest(draftReady, acknowledged),
        buildSendReplyRequest(draftReady, acknowledged),
      ),
    ).toBe(true);
  });

  it.each([
    ["another text", startEditing(acknowledged, "x")],
    ["another acknowledgement", opened],
  ])("does not match a reply with %s", (_case, state) => {
    expect(
      isSameReply(
        buildSendReplyRequest(draftReady, acknowledged),
        buildSendReplyRequest(draftReady, state),
      ),
    ).toBe(false);
  });

  it("does not match a rejection with other reason codes", () => {
    const first = buildSendReplyRequest(draftReady, {
      ...rejected,
      reasonCodes: new Set(["wrong_intent"]),
    });
    const second = buildSendReplyRequest(draftReady, {
      ...rejected,
      reasonCodes: new Set(["kb_gap"]),
    });

    expect(isSameReply(first, second)).toBe(false);
  });
});
