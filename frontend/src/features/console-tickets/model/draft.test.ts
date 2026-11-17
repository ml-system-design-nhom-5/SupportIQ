import { describe, expect, it } from "vitest";

import type { ReadyDraftContract } from "@/features/console-tickets/api/contract-types";
import { toDraftPart } from "@/features/console-tickets/model/draft";
import { readOperationExample } from "@/test/contract-examples";

/**
 * Read the draft of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The draft part.
 */
function readDraft(name: string) {
  const draft = readOperationExample("getConsoleTicket", 200, name).suggestion?.draft;
  if (draft === undefined) {
    throw new Error(`The example ${name} has no suggestion.`);
  }
  return draft;
}

/**
 * Read the ready draft of the draft-ready example.
 *
 * @returns The draft.
 */
function readReadyDraft(): ReadyDraftContract {
  const draft = readDraft("draft-ready");
  if (draft.draft_status !== "draft_ready") {
    throw new Error("The draft-ready example has no ready draft.");
  }
  return draft;
}

/** The draft of the draft-ready example as the console shows it. */
const draftReadyPart = {
  status: "draft_ready",
  segments: [
    {
      segmentId: "s1",
      paragraphIndex: 0,
      text: "Hello Lan Tran, thank you for your patience.",
      citationIds: [],
    },
    {
      segmentId: "s2",
      paragraphIndex: 1,
      text: "Your refund request for order ORD-20931 is under review.",
      citationIds: ["c2"],
    },
    {
      segmentId: "s3",
      paragraphIndex: 1,
      text: "This sample sentence stands for a policy statement from the cited document.",
      citationIds: ["c1"],
    },
  ],
  citations: [
    {
      kind: "kb_document",
      citationId: "c1",
      documentId: "SAMPLE-REFUND-001",
      version: "1.0",
      snippet: "This is sample text. It is not KB content and not a policy.",
    },
    {
      kind: "order_context",
      citationId: "c2",
      fact: { term: "Refund status", value: "Refund under review" },
    },
  ],
  text: "Hello Lan Tran, thank you for your patience.\n\nYour refund request for order ORD-20931 is under review. This sample sentence stands for a policy statement from the cited document.",
  reasonCodes: [],
};

describe("toDraftPart", () => {
  it("maps a ready draft with its segments, a KB citation, and an order citation", () => {
    expect(toDraftPart(readReadyDraft())).toEqual(draftReadyPart);
  });

  it("keeps the staff note of a ready draft", () => {
    expect(toDraftPart({ ...readReadyDraft(), staff_note: "Check the return." })).toHaveProperty(
      "staffNote",
      "Check the return.",
    );
  });

  it.each([
    [
      "abstained-low-confidence",
      {
        status: "abstained",
        reasonCodes: ["low_confidence"],
        staffNote: "The intent is uncertain. Confirm the intent or choose another to get a draft.",
      },
    ],
    ["llm-unavailable", { status: "llm_unavailable", reasonCodes: ["llm_unavailable"] }],
    ["ai-service-unavailable", { status: "unavailable", reasonCode: "ai_service_unavailable" }],
    ["suggestion-pending", { status: "pending" }],
  ])("maps the draft of the %s example", (name, part) => {
    expect(toDraftPart(readDraft(name))).toEqual(part);
  });

  it("maps an escalation recommendation with its reason code", () => {
    expect(toDraftPart(readDraft("escalated"))).toMatchObject({
      status: "escalation_recommended",
      reasonCodes: ["human_agent_requested"],
    });
  });
});

describe("toDraftPart of unknown values (CON-22)", () => {
  it("maps a draft status that this version does not know to unavailable (CON-22)", () => {
    expect(Reflect.apply(toDraftPart, undefined, [{ draft_status: "queued" }])).toEqual({
      status: "unavailable",
      reasonCode: "unknown",
    });
  });

  it.each([
    ["a kind", { source_type: "web_page", citation_id: "c9" }],
    [
      "an order field",
      { source_type: "order_context", citation_id: "c9", field: "warehouse", value: "W" },
    ],
  ])("ignores a citation of %s that this version does not know (CON-22)", (_case, citation) => {
    const part: unknown = Reflect.apply(toDraftPart, undefined, [
      { ...readReadyDraft(), citations: [citation] },
    ]);

    expect(part).toHaveProperty("citations", []);
  });
});
