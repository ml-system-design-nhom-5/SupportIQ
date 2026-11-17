import { describe, expect, it } from "vitest";

import { readField } from "@/features/console-tickets/model/json-text";
import {
  canFollowProgress,
  parseSuggestionProgress,
} from "@/features/console-tickets/model/suggestion-progress";
import { toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { readExample, readOperationExample } from "@/test/contract-examples";

/** The current suggestion of the examples. */
const SUGGESTION_ID = "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20";

/**
 * Write the data of an event.
 *
 * @param analysisStatus - The `analysis_status`.
 * @param draftStatus - The `draft_status`.
 * @returns The data as the stream sends it.
 */
function eventData(analysisStatus: string, draftStatus: string): string {
  return JSON.stringify({
    suggestion_id: SUGGESTION_ID,
    analysis_status: analysisStatus,
    draft_status: draftStatus,
  });
}

/**
 * Read a workspace example with some top-level members replaced.
 *
 * @param name - The example of `getConsoleTicket`.
 * @param overrides - The members to replace.
 * @returns The workspace.
 */
function workspaceOf(name: string, overrides: Readonly<Record<string, unknown>> = {}) {
  return toTicketWorkspace({
    ...readOperationExample("getConsoleTicket", 200, name),
    ...overrides,
  });
}

describe("parseSuggestionProgress", () => {
  it("reads the event of the contract example", () => {
    const data = readField(readExample("getSuggestionEvents", "draft-ready"), "data");

    expect(typeof data === "string" ? parseSuggestionProgress(data) : undefined).toEqual({
      suggestionId: SUGGESTION_ID,
      hasPendingPart: false,
    });
  });

  it.each([
    ["pending", "pending"],
    ["ready", "pending"],
  ])("counts a part as pending for the statuses %s and %s", (analysis, draft) => {
    expect(parseSuggestionProgress(eventData(analysis, draft))?.hasPendingPart).toBe(true);
  });

  it("counts an unknown status as done (CON-22)", () => {
    expect(parseSuggestionProgress(eventData("ready", "reviewed"))?.hasPendingPart).toBe(false);
  });

  it("gives nothing for data that is not JSON", () => {
    expect(parseSuggestionProgress("{suggestion")).toBeUndefined();
  });

  it.each(["null", "42", '"pending"', "[]"])("gives nothing for the JSON %s", (data) => {
    expect(parseSuggestionProgress(data)).toBeUndefined();
  });

  it("gives nothing for an event whose fields have the wrong type", () => {
    const data = JSON.stringify({ suggestion_id: 7, analysis_status: "ready", draft_status: null });

    expect(parseSuggestionProgress(data)).toBeUndefined();
  });
});

describe("canFollowProgress", () => {
  it("follows an open ticket in assisted mode with a pending part", () => {
    expect(canFollowProgress(workspaceOf("suggestion-pending"))).toBe(true);
  });

  it.each([
    ["a ticket without a pending part", workspaceOf("draft-ready")],
    ["a ticket in manual mode", workspaceOf("suggestion-pending", { handling_mode: "manual" })],
    ["a ticket that is not open", workspaceOf("suggestion-pending", { status: "escalated" })],
  ])("does not follow %s", (_case, workspace) => {
    expect(canFollowProgress(workspace)).toBe(false);
  });
});
