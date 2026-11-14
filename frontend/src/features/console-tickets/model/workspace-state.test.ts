import { describe, expect, it } from "vitest";

import type { AnalysisPart } from "@/features/console-tickets/model/analysis";
import type { DraftPart } from "@/features/console-tickets/model/draft";
import {
  type TicketWorkspace,
  toTicketWorkspace,
} from "@/features/console-tickets/model/workspace";
import {
  getReplyAreaState,
  getShownDraft,
  getSidebarState,
  hasPendingPart,
} from "@/features/console-tickets/model/workspace-state";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

/**
 * Map a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The view model.
 */
function readWorkspace(name: string): TicketWorkspace {
  return toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name));
}

/**
 * Replace parts of the suggestion of a workspace, for the states that no example covers yet.
 *
 * @param name - The example of `getConsoleTicket`.
 * @param parts - The analysis or the draft to put in.
 * @returns The workspace.
 */
function withParts(
  name: string,
  parts: { readonly analysis?: AnalysisPart; readonly draft?: DraftPart },
): TicketWorkspace {
  const workspace = readWorkspace(name);
  if (workspace.suggestion === undefined) {
    throw new Error(`The example ${name} has no suggestion.`);
  }
  return { ...workspace, suggestion: { ...workspace.suggestion, ...parts } };
}

describe("getReplyAreaState", () => {
  it.each([
    ["draft-ready", "draft"],
    ["suggestion-pending", "pending"],
    ["abstained-low-confidence", "choose_intent"],
    ["manual-mode", "manual_mode"],
    ["closed", "sent"],
    ["awaiting-approval", "proposal"],
    ["read-only-for-staff", "proposal"],
    ["escalated", "escalated"],
  ])("shows the %s example as %s", (name, kind) => {
    expect(getReplyAreaState(readWorkspace(name)).kind).toBe(kind);
  });

  it.each([
    ["ai-service-unavailable", "ai_service_unavailable"],
    ["pseudonymization-failed", "pseudonymization_failed"],
    ["llm-unavailable", "llm_unavailable"],
  ])("handles the %s example manually, with the reason", (name, reasonCode) => {
    expect(getReplyAreaState(readWorkspace(name))).toEqual({ kind: "ai_unavailable", reasonCode });
  });
});

describe("getReplyAreaState of states that no example covers", () => {
  it("shows the skeleton when the analysis is ready and the draft is pending (partial)", () => {
    expect(getReplyAreaState(withParts("draft-ready", { draft: { status: "pending" } }))).toEqual({
      kind: "pending",
    });
  });

  it.each([
    ["abstained", ["no_valid_document"]],
    ["escalation_recommended", ["human_agent_requested"]],
  ] as const)("shows the reason codes of a draft that is %s", (status, reasonCodes) => {
    const workspace = withParts("draft-ready", { draft: { status, reasonCodes } });

    expect(getReplyAreaState(workspace)).toEqual({ kind: "no_draft", status, reasonCodes });
  });

  it("handles a draft that failed without a reason code as unavailable", () => {
    const workspace = withParts("draft-ready", {
      draft: { status: "llm_unavailable", reasonCodes: [] },
    });

    expect(getReplyAreaState(workspace)).toEqual({
      kind: "ai_unavailable",
      reasonCode: "llm_unavailable",
    });
  });

  it("handles an assisted ticket without a suggestion manually", () => {
    const workspace = withoutMembers(readWorkspace("draft-ready"), ["suggestion"]);

    expect(getReplyAreaState(workspace).kind).toBe("manual_mode");
  });
});

describe("getSidebarState", () => {
  it("shows the analysis with the recommendation of a ready draft", () => {
    expect(getSidebarState(readWorkspace("draft-ready"))).toMatchObject({
      kind: "analysis",
      recommendation: "draft",
    });
  });

  it("asks staff to choose an intent after an abstention for low confidence, with the staff note", () => {
    expect(getSidebarState(readWorkspace("abstained-low-confidence"))).toMatchObject({
      kind: "analysis",
      recommendation: "choose_intent",
      staffNote: "The intent is uncertain. Confirm the intent or choose another to get a draft.",
    });
  });

  it("says that drafting failed after the analysis", () => {
    expect(getSidebarState(readWorkspace("llm-unavailable"))).toMatchObject({
      kind: "analysis",
      draftFailure: "llm_unavailable",
    });
  });
});

describe("getSidebarState of the other examples", () => {
  it.each([
    ["suggestion-pending", { kind: "loading" }],
    ["manual-mode", { kind: "manual_mode" }],
    ["ai-service-unavailable", { kind: "ai_unavailable", reasonCode: "ai_service_unavailable" }],
  ])("shows the %s example as %j", (name, state) => {
    expect(getSidebarState(readWorkspace(name))).toEqual(state);
  });

  it("recommends an escalation and keeps an abstention for another reason", () => {
    expect(getSidebarState(readWorkspace("escalated"))).toMatchObject({
      recommendation: "escalate",
    });
    expect(
      getSidebarState(
        withParts("draft-ready", {
          analysis: {
            status: "ready",
            alternatives: [],
            documents: [],
            recommendation: "abstain",
            reasonCodes: ["no_valid_document"],
            warnings: [],
          },
        }),
      ),
    ).toMatchObject({ recommendation: "abstain" });
  });
});

describe("hasPendingPart", () => {
  it.each([
    ["suggestion-pending", true],
    ["draft-ready", false],
    ["manual-mode", false],
  ])("tells whether the %s example has a pending part: %s", (name, isPending) => {
    expect(hasPendingPart(readWorkspace(name))).toBe(isPending);
  });

  it("is true while only the draft is pending", () => {
    expect(hasPendingPart(withParts("draft-ready", { draft: { status: "pending" } }))).toBe(true);
  });
});

describe("getReplyAreaState of a ticket handed to a manager", () => {
  it("shows the proposal with the ready AI draft for comparison", () => {
    const state = getReplyAreaState(readWorkspace("awaiting-approval"));

    expect(state).toMatchObject({
      kind: "proposal",
      proposal: { proposalId: "3e5a7c9b-1d2f-4a6c-8e0b-5d7f9a1c3e52" },
      draft: { status: "draft_ready" },
    });
    expect(getShownDraft(state)).toMatchObject({ status: "draft_ready" });
  });

  it("shows the draft of an escalated ticket whose draft is ready, as a reply needs it", () => {
    const { suggestion } = readWorkspace("draft-ready");
    const workspace = {
      ...readWorkspace("escalated"),
      ...(suggestion === undefined ? {} : { suggestion }),
    };

    expect(getReplyAreaState(workspace).kind).toBe("draft");
  });

  it("shows the escalation of an escalated ticket without a ready draft", () => {
    expect(getReplyAreaState(readWorkspace("escalated"))).toMatchObject({
      kind: "escalated",
      escalation: { reasonCodes: ["other"], escalatedBy: { displayName: "Mai Nguyen" } },
    });
  });
});
