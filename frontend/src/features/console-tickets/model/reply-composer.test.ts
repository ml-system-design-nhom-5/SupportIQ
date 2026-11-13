import { describe, expect, it } from "vitest";

import {
  acknowledgeWarning,
  discardEdits,
  initialComposerState,
  rejectDraft,
  startEditing,
  toggleReasonCode,
} from "@/features/console-tickets/model/reply-composer";

describe("the draft modes", () => {
  it("puts the draft's text in the editor, and discards the edits", () => {
    const editing = startEditing(initialComposerState, "Thank you for your patience.");

    expect(editing).toMatchObject({ draftMode: "editing", body: "Thank you for your patience." });
    expect(discardEdits(editing)).toMatchObject({ draftMode: "viewing", body: "" });
  });

  it("rejects the draft with an empty editor and no reason yet", () => {
    const edited = toggleReasonCode(startEditing(initialComposerState, "Edited."), "kb_gap");

    expect(rejectDraft({ ...edited, note: "A note." })).toMatchObject({
      draftMode: "rejecting",
      body: "",
      reasonCodes: new Set(),
      note: "",
    });
  });
});

describe("toggleReasonCode", () => {
  it("adds a code, and removes it when pressed again", () => {
    const chosen = toggleReasonCode(initialComposerState, "wrong_intent");

    expect(chosen.reasonCodes).toEqual(new Set(["wrong_intent"]));
    expect(toggleReasonCode(chosen, "wrong_intent").reasonCodes).toEqual(new Set());
  });
});

describe("acknowledgeWarning", () => {
  it("acknowledges a warning, and takes the acknowledgement back", () => {
    const acknowledged = acknowledgeWarning(initialComposerState, {
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
