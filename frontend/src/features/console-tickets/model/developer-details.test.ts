import { describe, expect, it } from "vitest";

import {
  buildDetailLines,
  toDeveloperDetails,
} from "@/features/console-tickets/model/developer-details";
import { readExampleSuggestion } from "@/test/console-screen";

/** The versions of every call of the examples. */
const sampleVersions = {
  releaseId: "release-2026-11-12-sample",
  modelVersion: "intent-model-sample-1",
  kbVersion: "kb-sample-1",
  mappingVersion: "mapping-sample-1",
  promptVersion: "prompts-sample-1",
  routingVersion: "routing-sample-1",
  indexVersion: "index-sample-1",
};

/** The developer details of the suggestion of the draft-ready example. */
const draftReadyDetails = {
  traceId: "4bf92f3577b34da6a3ce929d0e0e4736",
  suggestionId: "6b1f0c3e-2a4d-4e8f-9b7c-1d3e5f7a9b20",
  trigger: "ticket_created",
  analysis: {
    kind: "called",
    status: "ready",
    reasonCodes: [],
    versions: sampleVersions,
    latencies: { totalMs: 181, analysisMs: 179 },
  },
  analysisWarningCodes: ["source_review_overdue"],
  draft: {
    kind: "called",
    status: "draft_ready",
    reasonCodes: [],
    versions: sampleVersions,
    latencies: { totalMs: 3420, analysisMs: 176, llmMs: 3205 },
  },
};

/**
 * List the terms of the lines of a part.
 *
 * @param lines - The lines.
 * @returns Their terms, in order.
 */
function readTerms(lines: readonly { readonly term: string }[]): readonly string[] {
  return lines.map((line) => line.term);
}

describe("toDeveloperDetails", () => {
  it("maps the trace, the raw statuses and codes, the versions, and the latencies", () => {
    expect(toDeveloperDetails(readExampleSuggestion("draft-ready"))).toEqual(draftReadyDetails);
  });

  it("keeps the routing codes of the analysis and a draft call without an LLM request", () => {
    const { analysis, draft } = toDeveloperDetails(readExampleSuggestion("escalated"));

    expect(analysis).toMatchObject({ kind: "called", reasonCodes: ["human_agent_requested"] });
    expect(draft).toMatchObject({
      kind: "called",
      status: "escalation_recommended",
      reasonCodes: ["human_agent_requested"],
      latencies: { totalMs: 174, analysisMs: 172 },
    });
  });

  it("has only the status of parts that are pending", () => {
    const details = toDeveloperDetails(readExampleSuggestion("suggestion-pending"));

    expect(details.analysis).toEqual({ kind: "pending", status: "pending" });
    expect(details.draft).toEqual({ kind: "pending", status: "pending" });
    expect(details.analysisWarningCodes).toEqual([]);
  });

  it("keeps the reason codes of parts that backend could not get, without a call", () => {
    const { analysis, draft } = toDeveloperDetails(readExampleSuggestion("ai-service-unavailable"));

    expect(analysis).toEqual({
      kind: "not_called",
      status: "unavailable",
      reasonCodes: ["ai_service_unavailable"],
    });
    expect(draft).toEqual({
      kind: "not_called",
      status: "unavailable",
      reasonCodes: ["ai_service_unavailable"],
    });
  });
});

describe("buildDetailLines", () => {
  it("lists the status, the codes, the warnings, the versions, and the latencies of a call", () => {
    const { analysis, analysisWarningCodes } = toDeveloperDetails(
      readExampleSuggestion("draft-ready"),
    );

    expect(buildDetailLines(analysis, analysisWarningCodes)).toEqual([
      { term: "Status", value: "ready", isIdentifier: false },
      { term: "Reason codes", value: "None", isIdentifier: false },
      { term: "Warnings", value: "source_review_overdue", isIdentifier: false },
      { term: "Release", value: "release-2026-11-12-sample", isIdentifier: true },
      { term: "Model", value: "intent-model-sample-1", isIdentifier: true },
      { term: "KB", value: "kb-sample-1", isIdentifier: true },
      { term: "Mapping", value: "mapping-sample-1", isIdentifier: true },
      { term: "Prompts", value: "prompts-sample-1", isIdentifier: true },
      { term: "Routing", value: "routing-sample-1", isIdentifier: true },
      { term: "Index", value: "index-sample-1", isIdentifier: true },
      { term: "Total time", value: "181 ms", isIdentifier: false },
      { term: "Analysis time", value: "179 ms", isIdentifier: false },
      { term: "LLM time", value: "No LLM call", isIdentifier: false },
    ]);
  });

  it("formats the LLM time of a draft that called the LLM, without warnings", () => {
    const lines = buildDetailLines(toDeveloperDetails(readExampleSuggestion("draft-ready")).draft);

    expect(lines).toContainEqual({ term: "LLM time", value: "3,205 ms", isIdentifier: false });
    expect(readTerms(lines)).not.toContain("Warnings");
  });

  it("has only the status of a pending part", () => {
    const { analysis } = toDeveloperDetails(readExampleSuggestion("suggestion-pending"));

    expect(buildDetailLines(analysis, [])).toEqual([
      { term: "Status", value: "pending", isIdentifier: false },
    ]);
  });

  it("has the status and the reason codes of a part without a call", () => {
    const { draft } = toDeveloperDetails(readExampleSuggestion("ai-service-unavailable"));

    expect(readTerms(buildDetailLines(draft))).toEqual(["Status", "Reason codes"]);
  });
});
