import { describe, expect, it } from "vitest";

import type { ReadyAnalysisContract } from "@/features/console-tickets/api/contract-types";
import { toAnalysisPart } from "@/features/console-tickets/model/analysis";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

/**
 * Read the ready analysis of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The analysis.
 */
function readReadyAnalysis(name: string): ReadyAnalysisContract {
  const analysis = readOperationExample("getConsoleTicket", 200, name).suggestion?.analysis;
  if (analysis?.analysis_status !== "ready") {
    throw new Error(`The example ${name} has no ready analysis.`);
  }
  return analysis;
}

/** The analysis of the draft-ready example as the console shows it. */
const draftReadyAnalysis = {
  status: "ready",
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
  documents: [
    {
      documentId: "SAMPLE-REFUND-001",
      version: "1.0",
      title: "Sample refund document",
      effectiveStartAt: "2026-01-01T00:00:00Z",
      effectiveEndAt: "2027-01-01T00:00:00Z",
      validity: "valid",
      rank: 1,
      snippet: "This is sample text. It is not KB content and not a policy.",
    },
  ],
  recommendation: "draft",
  reasonCodes: [],
  warnings: [
    {
      warningId: "w1",
      reasonCode: "source_review_overdue",
      text: "A source that the AI found is past its review date. Check that it still applies.",
    },
  ],
};

describe("toAnalysisPart", () => {
  it("maps a ready analysis with a predicted intent, documents, and a warning", () => {
    expect(toAnalysisPart(readReadyAnalysis("draft-ready"))).toEqual(draftReadyAnalysis);
  });

  it("maps an intent that staff chose, without a band", () => {
    expect(toAnalysisPart(readReadyAnalysis("intent-corrected"))).toMatchObject({
      intent: { source: "staff", intent: { label: "refund_status", name: "Refund status" } },
      alternatives: [],
    });
  });

  it("maps a recommendation to escalate with its reason code", () => {
    expect(toAnalysisPart(readReadyAnalysis("escalated"))).toMatchObject({
      recommendation: "escalate",
      reasonCodes: ["human_agent_requested"],
    });
  });

  it("maps an open-ended document version", () => {
    const analysis = readReadyAnalysis("draft-ready");

    const part = toAnalysisPart({
      ...analysis,
      documents: analysis.documents.map((document) =>
        withoutMembers(document, ["effective_end_at"]),
      ),
    });

    expect(part).toMatchObject({ documents: [{ documentId: "SAMPLE-REFUND-001" }] });
    expect(part).not.toHaveProperty("documents.0.effectiveEndAt");
  });
});

describe("toAnalysisPart of other statuses and unknown values", () => {
  it.each([
    ["pending", { analysis_status: "pending" }, { status: "pending" }],
    [
      "unavailable",
      { analysis_status: "unavailable", reason_codes: ["ai_service_unavailable"] },
      { status: "unavailable", reasonCode: "ai_service_unavailable" },
    ],
    [
      "of an unknown status",
      { analysis_status: "paused" },
      { status: "unavailable", reasonCode: "unknown" },
    ],
  ])("maps an analysis that is %s", (_case, analysis, part) => {
    expect(Reflect.apply(toAnalysisPart, undefined, [analysis])).toEqual(part);
  });
});

describe("toAnalysisPart of values that this version does not know", () => {
  it("maps an intent source that this version does not know to no known intent (CON-22)", () => {
    const part: unknown = Reflect.apply(toAnalysisPart, undefined, [
      { ...readReadyAnalysis("draft-ready"), intent: { source: "rules", label: "refund_status" } },
    ]);

    expect(part).toHaveProperty("status", "ready");
    expect(part).not.toHaveProperty("intent");
  });

  it("maps a recommendation that this version does not know to abstain (CON-22)", () => {
    const part: unknown = Reflect.apply(toAnalysisPart, undefined, [
      {
        ...readReadyAnalysis("draft-ready"),
        routing: { recommendation: "wait", reason_codes: [] },
      },
    ]);

    expect(part).toHaveProperty("recommendation", "abstain");
  });

  it("maps a validity that this version does not know to expired, never usable (CON-22)", () => {
    const analysis = readReadyAnalysis("draft-ready");

    const part: unknown = Reflect.apply(toAnalysisPart, undefined, [
      {
        ...analysis,
        documents: analysis.documents.map((document) => ({ ...document, validity: "draft" })),
      },
    ]);

    expect(part).toMatchObject({ documents: [{ validity: "expired" }] });
  });
});
