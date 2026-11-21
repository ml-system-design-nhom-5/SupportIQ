import { describe, expect, it } from "vitest";

import {
  getChoosableLabel,
  getIntentAreaState,
  listOtherIntents,
} from "@/features/console-tickets/model/intent-area";
import {
  type TicketWorkspace,
  toSuggestion,
  toTicketWorkspace,
} from "@/features/console-tickets/model/workspace";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

/** How many intents the contract lists. */
const INTENT_COUNT = 46;

/**
 * Show the intent strip of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The state of the strip.
 */
function readIntentArea(name: string) {
  return getIntentAreaState(toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name)));
}

/**
 * Read the draft-ready workspace with an analysis whose intent source is unknown, so it has no
 * known intent (CON-22).
 *
 * @returns The workspace.
 */
function readWorkspaceWithoutIntent(): TicketWorkspace {
  const workspace = toTicketWorkspace(readOperationExample("getConsoleTicket", 200, "draft-ready"));
  const suggestion = workspace.suggestion;
  if (suggestion?.analysis.status !== "ready") {
    throw new Error("The draft-ready example has no ready analysis.");
  }
  return {
    ...workspace,
    suggestion: { ...suggestion, analysis: withoutMembers(suggestion.analysis, ["intent"]) },
  };
}

/**
 * Read the draft-ready workspace with its draft still generating (the partial state), which keeps
 * `correct_intent` among its actions.
 *
 * @returns The workspace.
 */
function readWorkspaceWithPendingDraft(): TicketWorkspace {
  const workspace = toTicketWorkspace(readOperationExample("getConsoleTicket", 200, "draft-ready"));
  if (workspace.suggestion === undefined) {
    throw new Error("The draft-ready example has no suggestion.");
  }
  return { ...workspace, suggestion: { ...workspace.suggestion, draft: { status: "pending" } } };
}

describe("getIntentAreaState", () => {
  it("shows the predicted intent with the next two candidates, correctable (FR-01, UI-22)", () => {
    expect(readIntentArea("draft-ready")).toEqual({
      kind: "intent",
      intent: {
        source: "model",
        intent: { label: "refund_status", name: "Refund status" },
        band: "high",
        probability: 0.88,
      },
      alternatives: [
        { intent: { label: "request_refund", name: "Request refund" }, probability: 0.07 },
        { intent: { label: "track_order", name: "Track order" }, probability: 0.02 },
      ],
      canCorrect: true,
    });
  });

  it("offers the top three candidates after an abstention for low confidence (UI-42)", () => {
    expect(readIntentArea("abstained-low-confidence")).toMatchObject({
      kind: "choose",
      intent: { band: "low", probability: 0.41 },
      canCorrect: true,
    });
  });

  it.each([
    ["suggestion-pending", "loading"],
    ["manual-mode", "none"],
    ["ai-service-unavailable", "none"],
  ])("shows the %s example as %s", (name, kind) => {
    expect(readIntentArea(name).kind).toBe(kind);
  });

  it("says that the intent is unknown when the analysis has no known intent", () => {
    expect(getIntentAreaState(readWorkspaceWithoutIntent()).kind).toBe("unknown");
  });
});

describe("getIntentAreaState and correct_intent", () => {
  it("shows the intent that staff chose, without candidates, and lets staff change it again", () => {
    expect(readIntentArea("intent-corrected")).toEqual({
      kind: "intent",
      intent: { source: "staff", intent: { label: "refund_status", name: "Refund status" } },
      alternatives: [],
      canCorrect: true,
    });
  });

  it("offers a correction while the draft is generating, as backend allows (UI-22)", () => {
    expect(getIntentAreaState(readWorkspaceWithPendingDraft())).toMatchObject({
      kind: "intent",
      canCorrect: true,
    });
  });

  it.each(["read-only-for-staff", "awaiting-approval"])(
    "offers no correction in the %s example, whose actions lack correct_intent (UI-40)",
    (name) => {
      expect(readIntentArea(name)).toMatchObject({ kind: "intent", canCorrect: false });
    },
  );
});

describe("getIntentAreaState while the analysis is pending", () => {
  it("keeps the intent that staff chose on the strip after a correction (UI-22)", () => {
    const workspace = toTicketWorkspace(
      readOperationExample("getConsoleTicket", 200, "draft-ready"),
    );
    const correction = toSuggestion(
      readOperationExample("createSuggestion", 202, "intent-override"),
    );

    expect(getIntentAreaState({ ...workspace, suggestion: correction })).toEqual({
      kind: "intent",
      intent: { source: "staff", intent: { label: "request_refund", name: "Request refund" } },
      alternatives: [],
      canCorrect: true,
    });
  });

  it("shows the skeleton when staff chose no intent", () => {
    expect(readIntentArea("suggestion-pending")).toEqual({ kind: "loading" });
  });
});

describe("listOtherIntents", () => {
  it("lists every intent but the one on the strip, by name", () => {
    const otherIntents = listOtherIntents({ label: "refund_status", name: "Refund status" });

    expect(otherIntents).toHaveLength(INTENT_COUNT - 1);
    expect(otherIntents.slice(0, 2)).toEqual([
      { label: "add_product", name: "Add product" },
      { label: "availability", name: "Availability" },
    ]);
    expect(otherIntents.map((intent) => intent.label)).not.toContain("refund_status");
  });

  it("lists every intent next to an intent that this version does not know", () => {
    expect(listOtherIntents({ label: "unknown", name: "Unspecified intent" })).toHaveLength(
      INTENT_COUNT,
    );
  });
});

describe("getChoosableLabel", () => {
  it.each([
    [{ label: "track_order", name: "Track order" }, "track_order"],
    [{ label: "unknown", name: "Unspecified intent" }, undefined],
  ] as const)("reads the label of %j as %s (CON-22)", (intent, label) => {
    expect(getChoosableLabel(intent)).toBe(label);
  });
});
