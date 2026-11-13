import { describe, expect, it } from "vitest";

import {
  initialComposerState,
  rejectDraft,
  startEditing,
} from "@/features/console-tickets/model/reply-composer";
import {
  buildSendReplyRequest,
  canChangeDraft,
  type ComposerTicket,
  isSameReply,
  toComposerTicket,
} from "@/features/console-tickets/model/reply-request";
import { toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { buildWorkspaceRegions } from "@/features/console-tickets/model/workspace-regions";
import { readOperationExample } from "@/test/contract-examples";

/** The current suggestion of the draft-ready and abstained-low-confidence examples. */
const SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";

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
      isSuggestionRunning: false,
      suggestionId: SUGGESTION_ID,
      draft: { suggestionId: SUGGESTION_ID },
      warningIds: ["w1"],
    });
    expect(draftReady.draft?.text).toMatch(/^Hello Lan Tran, thank you for your patience\./);
  });

  it("has no suggestion and no draft in manual mode", () => {
    const manual = readTicket("manual-mode");

    expect(manual).not.toHaveProperty("suggestionId");
    expect(manual).not.toHaveProperty("draft");
  });

  it("says that the AI is running while a part is pending", () => {
    expect(readTicket("suggestion-pending")).toMatchObject({ isSuggestionRunning: true });
    expect(readTicket("suggestion-pending")).not.toHaveProperty("draft");
  });
});

describe("buildSendReplyRequest of a ready draft", () => {
  it("sends the draft as is with the basis ai_draft and every warning acknowledged", () => {
    expect(buildSendReplyRequest(draftReady, initialComposerState)).toEqual({
      basis: "ai_draft",
      body: draftReady.draft?.text,
      suggestion_id: SUGGESTION_ID,
      acknowledged_warning_ids: ["w1"],
    });
  });

  it("sends the edited text with the basis ai_draft", () => {
    expect(
      buildSendReplyRequest(draftReady, startEditing(initialComposerState, "Edited reply.")),
    ).toMatchObject({ basis: "ai_draft", body: "Edited reply." });
  });
});

describe("buildSendReplyRequest of a rejected draft", () => {
  it("sends the reason codes in the order of the contract, without a note", () => {
    const rejected = rejectDraft(initialComposerState);

    expect(
      buildSendReplyRequest(draftReady, {
        ...rejected,
        body: "My own reply.",
        reasonCodes: new Set(["unsupported_claim", "wrong_intent"]),
      }),
    ).toEqual({
      basis: "rejected_ai_draft",
      body: "My own reply.",
      suggestion_id: SUGGESTION_ID,
      staff_reason_codes: ["wrong_intent", "unsupported_claim"],
    });
  });

  it("sends the note of the reason code other", () => {
    expect(
      buildSendReplyRequest(draftReady, {
        ...rejectDraft(initialComposerState),
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
      buildSendReplyRequest(readTicket("abstained-low-confidence"), {
        ...initialComposerState,
        body: "My reply.",
      }),
    ).toEqual({ basis: "no_ai_draft", body: "My reply.", suggestion_id: SUGGESTION_ID });
  });

  it("sends the basis no_ai_draft without a suggestion in manual mode", () => {
    expect(
      buildSendReplyRequest(readTicket("manual-mode"), { ...initialComposerState, body: "Hi." }),
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
    expect(canChangeDraft(readTicket(name))).toBe(canChange);
  });
});

describe("isSameReply", () => {
  it("matches the same reply confirmed again, and not a changed one", () => {
    const first = buildSendReplyRequest(draftReady, initialComposerState);

    expect(isSameReply(first, buildSendReplyRequest(draftReady, initialComposerState))).toBe(true);
    expect(
      isSameReply(
        first,
        buildSendReplyRequest(draftReady, startEditing(initialComposerState, "x")),
      ),
    ).toBe(false);
  });
});
