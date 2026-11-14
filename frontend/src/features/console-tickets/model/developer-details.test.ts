import { describe, expect, it } from "vitest";

import {
  describePartDetails,
  toDeveloperDetails,
} from "@/features/console-tickets/model/developer-details";
import { readOperationExample } from "@/test/contract-examples";

/**
 * Read the suggestion of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns Its suggestion.
 */
function readSuggestion(name: string) {
  const { suggestion } = readOperationExample("getConsoleTicket", 200, name);
  if (suggestion === undefined) {
    throw new Error(`The example ${name} has no suggestion.`);
  }
  return suggestion;
}

/** The versions of every part of the examples. */
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
    part: "analysis",
    status: "ready",
    reasonCodes: [],
    warningCodes: ["source_review_overdue"],
    versions: sampleVersions,
    latencies: { totalMs: 181, analysisMs: 179 },
  },
  draft: {
    part: "draft",
    status: "draft_ready",
    reasonCodes: [],
    warningCodes: [],
    versions: sampleVersions,
    latencies: { totalMs: 3420, analysisMs: 176, llmMs: 3205 },
  },
};

describe("toDeveloperDetails", () => {
  it("maps the trace, the raw statuses and codes, the versions, and the latencies", () => {
    expect(toDeveloperDetails(readSuggestion("draft-ready"))).toEqual(draftReadyDetails);
  });

  it("keeps the routing codes of the analysis and a draft without an LLM call", () => {
    const { analysis, draft } = toDeveloperDetails(readSuggestion("escalated"));

    expect(analysis.reasonCodes).toEqual(["human_agent_requested"]);
    expect(draft).toMatchObject({
      status: "escalation_recommended",
      reasonCodes: ["human_agent_requested"],
      latencies: { totalMs: 174, analysisMs: 172 },
    });
    expect(draft.latencies).not.toHaveProperty("llmMs");
  });

  it("has no versions or latencies for parts that are pending", () => {
    const { analysis, draft } = toDeveloperDetails(readSuggestion("suggestion-pending"));

    expect(analysis).toEqual({
      part: "analysis",
      status: "pending",
      reasonCodes: [],
      warningCodes: [],
    });
    expect(draft).toEqual({ part: "draft", status: "pending", reasonCodes: [], warningCodes: [] });
  });

  it("keeps the reason codes of parts that backend could not get", () => {
    const { analysis, draft } = toDeveloperDetails(readSuggestion("ai-service-unavailable"));

    expect(analysis).toEqual({
      part: "analysis",
      status: "unavailable",
      reasonCodes: ["ai_service_unavailable"],
      warningCodes: [],
    });
    expect(draft).toMatchObject({ status: "unavailable", reasonCodes: ["ai_service_unavailable"] });
  });
});

describe("describePartDetails", () => {
  it("lists the status, the codes, the warnings, the versions, and the latencies of a call", () => {
    const { analysis } = toDeveloperDetails(readSuggestion("draft-ready"));

    expect(describePartDetails(analysis)).toEqual([
      { term: "Status", value: "ready" },
      { term: "Reason codes", value: "None" },
      { term: "Warnings", value: "source_review_overdue" },
      { term: "Release", value: "release-2026-11-12-sample" },
      { term: "Model", value: "intent-model-sample-1" },
      { term: "KB", value: "kb-sample-1" },
      { term: "Mapping", value: "mapping-sample-1" },
      { term: "Prompts", value: "prompts-sample-1" },
      { term: "Routing", value: "routing-sample-1" },
      { term: "Index", value: "index-sample-1" },
      { term: "Total time", value: "181 ms" },
      { term: "Analysis time", value: "179 ms" },
      { term: "LLM time", value: "No LLM call" },
    ]);
  });

  it("formats the LLM time of a draft that called the LLM", () => {
    const { draft } = toDeveloperDetails(readSuggestion("draft-ready"));

    expect(describePartDetails(draft)).toContainEqual({ term: "LLM time", value: "3,205 ms" });
    expect(describePartDetails(draft).map((line) => line.term)).not.toContain("Warnings");
  });

  it.each(["suggestion-pending", "ai-service-unavailable"])(
    "has only the status and the codes of a part without a call (%s)",
    (name) => {
      const { analysis, draft } = toDeveloperDetails(readSuggestion(name));

      expect(describePartDetails(analysis).map((line) => line.term)).toEqual([
        "Status",
        "Reason codes",
      ]);
      expect(describePartDetails(draft).map((line) => line.term)).toEqual([
        "Status",
        "Reason codes",
      ]);
    },
  );
});
