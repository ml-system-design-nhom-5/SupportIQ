import { describe, expect, it } from "vitest";

import {
  acknowledgeWarning,
  type ComposerState,
  createComposerState,
  discardEdits,
  followSuggestion,
  rejectDraft,
  startEditing,
  toggleReasonCode,
} from "@/features/console-tickets/model/reply-composer";

const opened = createComposerState("s1");

/**
 * Compose on the first suggestion: acknowledge its warning and choose a reason code.
 *
 * @param state - The state to start from.
 * @returns The state with the acknowledgement, the code, and a note.
 */
function checkOnFirstSuggestion(state: ComposerState): ComposerState {
  const acknowledged = acknowledgeWarning(state, { warningId: "w1", isAcknowledged: true });
  return { ...toggleReasonCode(acknowledged, "other"), note: "A note." };
}

describe("the draft modes", () => {
  it("opens with the draft read as is, for the current suggestion", () => {
    expect(opened).toMatchObject({ suggestionId: "s1", draftMode: "viewing", body: "" });
  });

  it("puts the draft's text in the editor, and discards the edits", () => {
    const editing = startEditing(opened, "Thank you for your patience.");

    expect(editing).toMatchObject({ draftMode: "editing", body: "Thank you for your patience." });
    expect(discardEdits(editing)).toMatchObject({ draftMode: "viewing", body: "" });
  });

  it("rejects the draft with an empty editor and no reason yet", () => {
    const edited = toggleReasonCode(startEditing(opened, "Edited."), "kb_gap");

    expect(rejectDraft({ ...edited, note: "A note." })).toMatchObject({
      draftMode: "rejecting",
      body: "",
      reasonCodes: new Set(),
      note: "",
    });
  });
});

describe("followSuggestion (UI-18, ADR-0006)", () => {
  it("keeps the same state while the suggestion is the same", () => {
    const checked = checkOnFirstSuggestion(opened);

    expect(followSuggestion(checked, { suggestionId: "s1", proposalId: undefined })).toBe(checked);
  });

  it("drops what staff checked on the old suggestion, and reads the new draft without text", () => {
    const rejected = checkOnFirstSuggestion(rejectDraft(opened));

    expect(followSuggestion(rejected, { suggestionId: "s2", proposalId: undefined })).toEqual(
      createComposerState("s2"),
    );
  });

  it("keeps an edit of the old draft in the editor, as an edit, under the new draft", () => {
    const edited = checkOnFirstSuggestion(startEditing(opened, "Edited reply."));

    expect(followSuggestion(edited, { suggestionId: "s2", proposalId: undefined })).toEqual({
      ...createComposerState("s2"),
      draftMode: "keeping",
      body: "Edited reply.",
      keptTextOrigin: "edited_draft",
    });
  });

  it.each([
    ["after a rejection", { ...rejectDraft(opened), body: "My own reply." }],
    ["without a draft", { ...opened, body: "My own reply." }],
  ])("keeps a reply that staff wrote %s as their own reply", (_case, state) => {
    expect(
      followSuggestion(checkOnFirstSuggestion(state), {
        suggestionId: "s2",
        proposalId: undefined,
      }),
    ).toMatchObject({
      draftMode: "keeping",
      body: "My own reply.",
      keptTextOrigin: "own_reply",
      reasonCodes: new Set(),
      note: "",
      acknowledgedWarningIds: new Set(),
    });
  });
});

describe("followSuggestion of a kept text", () => {
  it("keeps where the text came from over several new drafts", () => {
    const kept = followSuggestion(startEditing(opened, "Edited reply."), {
      suggestionId: "s2",
      proposalId: undefined,
    });

    expect(followSuggestion(kept, { suggestionId: "s3", proposalId: undefined })).toMatchObject({
      suggestionId: "s3",
      draftMode: "keeping",
      keptTextOrigin: "edited_draft",
    });
  });

  it("starts over when a proposal arrives on the same suggestion (FR-06)", () => {
    const edited = startEditing(opened, "A manager's own text.");

    expect(followSuggestion(edited, { suggestionId: "s1", proposalId: "p1" })).toEqual(
      createComposerState("s1", "p1"),
    );
  });

  it("starts over when another proposal replaces the one that a manager edits", () => {
    const editing = startEditing(createComposerState("s1", "p1"), "Edited proposal.");

    expect(followSuggestion(editing, { suggestionId: "s1", proposalId: "p2" })).toEqual(
      createComposerState("s1", "p2"),
    );
  });

  it("treats a text of spaces only as no text", () => {
    expect(
      followSuggestion({ ...opened, body: "  " }, { suggestionId: "s2", proposalId: undefined }),
    ).toEqual(createComposerState("s2"));
  });
});

describe("the kept text", () => {
  const kept = followSuggestion(
    { ...rejectDraft(opened), body: "My own reply." },
    { suggestionId: "s2", proposalId: undefined },
  );

  it("stays in the editor when staff reject the new draft", () => {
    expect(rejectDraft(kept)).toMatchObject({
      draftMode: "rejecting",
      body: "My own reply.",
      keptTextOrigin: undefined,
    });
  });

  it("is replaced by the new draft on Edit draft, and dropped on Discard edits", () => {
    expect(startEditing(kept, "New draft.")).toMatchObject({
      draftMode: "editing",
      body: "New draft.",
      keptTextOrigin: undefined,
    });
    expect(discardEdits(kept)).toMatchObject({
      draftMode: "viewing",
      body: "",
      keptTextOrigin: undefined,
    });
  });
});

describe("toggleReasonCode", () => {
  it("adds a code, and removes it when pressed again", () => {
    const chosen = toggleReasonCode(opened, "wrong_intent");

    expect(chosen.reasonCodes).toEqual(new Set(["wrong_intent"]));
    expect(toggleReasonCode(chosen, "wrong_intent").reasonCodes).toEqual(new Set());
  });
});

describe("acknowledgeWarning", () => {
  it("acknowledges a warning, and takes the acknowledgement back", () => {
    const acknowledged = acknowledgeWarning(opened, {
      warningId: "w1",
      isAcknowledged: true,
    });

    expect(acknowledged.acknowledgedWarningIds).toEqual(new Set(["w1"]));
    expect(
      acknowledgeWarning(acknowledged, { warningId: "w1", isAcknowledged: false })
        .acknowledgedWarningIds,
    ).toEqual(new Set());
  });
});
