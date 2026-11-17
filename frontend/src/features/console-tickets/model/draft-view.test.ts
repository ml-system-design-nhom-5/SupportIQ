import { describe, expect, it } from "vitest";

import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import { buildDraftParagraphs } from "@/features/console-tickets/model/draft-view";
import { buildDocumentKey, numberCitedDocuments } from "@/features/console-tickets/model/sources";

/** A draft with two paragraphs, a version cited twice in one segment, and an order citation. */
const draft: ReadyDraft = {
  status: "draft_ready",
  segments: [
    { segmentId: "s1", paragraphIndex: 0, text: "Hello.", citationIds: [] },
    { segmentId: "s2", paragraphIndex: 1, text: "Your refund is paid.", citationIds: ["c2"] },
    { segmentId: "s3", paragraphIndex: 1, text: "Refunds take time.", citationIds: ["c1", "c3"] },
    { segmentId: "s4", paragraphIndex: 3, text: "Goodbye.", citationIds: ["c-missing"] },
  ],
  citations: [
    { kind: "kb_document", citationId: "c1", documentId: "DOC-A", version: "1", snippet: "A1" },
    { kind: "order_context", citationId: "c2", fact: { term: "Refund status", value: "Paid" } },
    { kind: "kb_document", citationId: "c3", documentId: "DOC-A", version: "1", snippet: "A2" },
  ],
  text: "Hello.\n\nYour refund is paid. Refunds take time.\n\nGoodbye.",
  reasonCodes: [],
};

/** The paragraphs of the draft, with the numbers of its citations. */
const paragraphs = buildDraftParagraphs(draft, numberCitedDocuments(draft));

describe("buildDraftParagraphs", () => {
  it("starts a new paragraph where the paragraph index changes", () => {
    expect(
      paragraphs.map((paragraph) => paragraph.segments.map((segment) => segment.segmentId)),
    ).toEqual([["s1"], ["s2", "s3"], ["s4"]]);
    expect(paragraphs.map((paragraph) => paragraph.paragraphId)).toEqual([
      "paragraph-0",
      "paragraph-1",
      "paragraph-3",
    ]);
  });

  it("gives a segment that states an order fact its facts, without a KB marker", () => {
    expect(paragraphs[1]?.segments[0]).toMatchObject({
      kbMarkers: [],
      orderFacts: [{ term: "Refund status", value: "Paid" }],
    });
  });

  it("gives a segment one marker per cited document version, with the first snippet", () => {
    expect(paragraphs[1]?.segments[1]?.kbMarkers).toEqual([
      {
        citationId: "c1",
        number: 1,
        documentKey: buildDocumentKey("DOC-A", "1"),
        documentId: "DOC-A",
        version: "1",
        snippet: "A1",
      },
    ]);
  });
});

describe("buildDraftParagraphs with citations that have no marker", () => {
  it("ignores a citation ID that names no citation", () => {
    expect(paragraphs[2]?.segments[0]).toMatchObject({ kbMarkers: [], orderFacts: [] });
  });

  it("shows no KB marker for a citation without a number", () => {
    const [firstParagraph] = buildDraftParagraphs(
      {
        ...draft,
        segments: [{ segmentId: "s9", paragraphIndex: 0, text: "x", citationIds: ["c1"] }],
      },
      new Map(),
    );

    expect(firstParagraph?.segments[0]?.kbMarkers).toEqual([]);
  });
});
