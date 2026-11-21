import { describe, expect, it } from "vitest";

import {
  buildKbDocumentDetails,
  toKbDocumentVersion,
} from "@/features/console-tickets/model/kb-document";
import { readOperationExample, withoutMembers } from "@/test/contract-examples";

const example = readOperationExample("getConsoleKbDocumentVersion", 200, "document-version");

describe("toKbDocumentVersion", () => {
  it("maps the full text and the details of a version", () => {
    expect(toKbDocumentVersion(example)).toEqual({
      documentId: "SAMPLE-REFUND-001",
      version: "1.0",
      title: "Sample refund document",
      body: "This is sample text. It is not KB content and not a policy. The approved KB files will replace it.",
      effectiveStartAt: "2026-01-01T00:00:00Z",
      effectiveEndAt: "2027-01-01T00:00:00Z",
      owner: "Policy owner (sample)",
      source: "Sample source document",
    });
  });

  it("keeps the last review when the source gives it", () => {
    expect(
      toKbDocumentVersion({ ...example, last_reviewed_at: "2026-06-01T00:00:00Z" }),
    ).toHaveProperty("lastReviewedAt", "2026-06-01T00:00:00Z");
  });
});

describe("buildKbDocumentDetails", () => {
  it("lists the effective period, the owner, and the source, without an invented review date", () => {
    expect(buildKbDocumentDetails(toKbDocumentVersion(example))).toEqual([
      { term: "In effect", value: "1 Jan 2026 to 1 Jan 2027" },
      { term: "Owner", value: "Policy owner (sample)" },
      { term: "Source", value: "Sample source document" },
    ]);
  });

  it("lists the last review and an open-ended period", () => {
    const document = toKbDocumentVersion({
      ...withoutMembers(example, ["effective_end_at"]),
      last_reviewed_at: "2026-06-01T00:00:00Z",
    });

    expect(buildKbDocumentDetails(document)).toEqual([
      { term: "In effect", value: "Since 1 Jan 2026" },
      { term: "Owner", value: "Policy owner (sample)" },
      { term: "Source", value: "Sample source document" },
      { term: "Last reviewed", value: "1 Jun 2026" },
    ]);
  });
});
