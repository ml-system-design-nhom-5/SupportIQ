import { describe, expect, it } from "vitest";

import type { RankedDocument } from "@/features/console-tickets/model/analysis";
import type { ReadyDraft } from "@/features/console-tickets/model/draft";
import {
  buildDocumentKey,
  buildSources,
  describeEffectiveDates,
  describeEffectivePeriod,
  numberCitedDocuments,
  type Source,
  toSourceSelection,
} from "@/features/console-tickets/model/sources";

/** A ranked document that a test overrides only where it matters (TEST-05). */
function buildDocument(overrides: Partial<RankedDocument>): RankedDocument {
  return {
    documentId: "SAMPLE-REFUND-001",
    version: "1.0",
    title: "Sample refund document",
    effectiveStartAt: "2026-01-01T00:00:00Z",
    validity: "valid",
    rank: 1,
    snippet: "Sample snippet.",
    ...overrides,
  };
}

/** A draft whose segments cite c3, then c1 and c2, then c1 again; c2 cites the order. */
const draft: ReadyDraft = {
  status: "draft_ready",
  segments: [
    { segmentId: "s1", paragraphIndex: 0, text: "First.", citationIds: ["c3"] },
    { segmentId: "s2", paragraphIndex: 1, text: "Second.", citationIds: ["c1", "c2"] },
    { segmentId: "s3", paragraphIndex: 1, text: "Third.", citationIds: ["c1", "c9"] },
  ],
  citations: [
    { kind: "kb_document", citationId: "c1", documentId: "DOC-A", version: "1", snippet: "A" },
    { kind: "order_context", citationId: "c2", fact: { term: "Refund status", value: "Paid" } },
    { kind: "kb_document", citationId: "c3", documentId: "DOC-B", version: "2", snippet: "B" },
  ],
  text: "First.\n\nSecond. Third.",
  reasonCodes: [],
};

describe("numberCitedDocuments", () => {
  it("numbers the cited document versions in reading order, once each", () => {
    expect([...numberCitedDocuments(draft)]).toEqual([
      [buildDocumentKey("DOC-B", "2"), 1],
      [buildDocumentKey("DOC-A", "1"), 2],
    ]);
  });

  it("numbers nothing without a draft", () => {
    expect(numberCitedDocuments(undefined).size).toBe(0);
  });
});

describe("buildSources", () => {
  it("lists the documents by rank, with the number of a cited version only", () => {
    const sources = buildSources(
      [
        buildDocument({ documentId: "DOC-C", version: "1", rank: 2 }),
        buildDocument({ documentId: "DOC-A", version: "1", rank: 1 }),
      ],
      numberCitedDocuments(draft),
    );

    expect(sources.map((source) => [source.documentId, source.number])).toEqual([
      ["DOC-A", 2],
      ["DOC-C", undefined],
    ]);
    expect(sources[1]).not.toHaveProperty("number");
  });
});

describe("describeEffectivePeriod", () => {
  it.each([
    ["an open-ended version", {}, "Since 1 Jan 2026"],
    [
      "a version in effect until a date",
      { effectiveEndAt: "2027-01-01T00:00:00Z" },
      "1 Jan 2026 to 1 Jan 2027",
    ],
    [
      "an expired version",
      { effectiveEndAt: "2026-09-30T00:00:00Z", validity: "expired" as const },
      "Ended 30 Sept 2026",
    ],
    ["an expired version without an end", { validity: "expired" as const }, "Since 1 Jan 2026"],
  ])("describes %s", (_case, overrides, period) => {
    expect(describeEffectivePeriod(buildDocument(overrides))).toBe(period);
  });
});

describe("describeEffectiveDates", () => {
  it.each([
    [undefined, "Since 1 Sept 2026"],
    ["2026-12-01T00:00:00Z", "1 Sept 2026 to 1 Dec 2026"],
  ])("describes the dates until %s", (end, text) => {
    expect(describeEffectiveDates("2026-09-01T00:00:00Z", end)).toBe(text);
  });
});

describe("toSourceSelection", () => {
  const source: Source = {
    key: "SAMPLE-REFUND-001 1.0",
    number: 1,
    documentId: "SAMPLE-REFUND-001",
    version: "1.0",
    title: "Sample refund document",
    validity: "valid",
    period: "Since 1 Jan 2026",
    snippet: "Retrieved passage.",
  };

  it("highlights the retrieved passage of a source of the Sources panel", () => {
    expect(toSourceSelection(source, source)).toEqual({
      documentId: "SAMPLE-REFUND-001",
      version: "1.0",
      title: "Sample refund document",
      highlight: "Retrieved passage.",
      source,
    });
  });

  it("highlights the cited passage of a marker, with the title of its source", () => {
    const marker = { documentId: "SAMPLE-REFUND-001", version: "1.0", snippet: "Cited passage." };

    expect(toSourceSelection(marker, source)).toEqual({
      documentId: "SAMPLE-REFUND-001",
      version: "1.0",
      title: "Sample refund document",
      highlight: "Cited passage.",
      source,
    });
  });

  it("titles a version that the analysis did not return with its document ID", () => {
    const marker = { documentId: "SAMPLE-OTHER-002", version: "2.0", snippet: "Cited passage." };

    expect(toSourceSelection(marker, undefined)).toEqual({
      documentId: "SAMPLE-OTHER-002",
      version: "2.0",
      title: "SAMPLE-OTHER-002",
      highlight: "Cited passage.",
    });
  });
});
