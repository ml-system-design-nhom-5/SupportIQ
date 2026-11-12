import { describe, expect, it } from "vitest";

import { getIntentAreaState } from "@/features/console-tickets/model/intent-area";
import {
  type TicketWorkspace,
  toTicketWorkspace,
} from "@/features/console-tickets/model/workspace";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

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

describe("getIntentAreaState", () => {
  it("shows the predicted intent with the next two candidates (FR-01)", () => {
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
    });
  });

  it("shows the intent that staff chose, without candidates", () => {
    expect(readIntentArea("intent-corrected")).toEqual({
      kind: "intent",
      intent: { source: "staff", intent: { label: "refund_status", name: "Refund status" } },
      alternatives: [],
    });
  });

  it("offers the top three candidates after an abstention for low confidence (UI-42)", () => {
    expect(readIntentArea("abstained-low-confidence")).toMatchObject({
      kind: "choose",
      intent: { band: "low", probability: 0.41 },
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
