import { describe, expect, it } from "vitest";

import { toTicketWorkspace } from "@/features/console-tickets/model/workspace";
import { buildWorkspaceRegions } from "@/features/console-tickets/model/workspace-regions";
import { readOperationExample } from "@/test/contract-examples";

/**
 * Build the regions of a workspace example.
 *
 * @param name - The example of `getConsoleTicket`.
 * @returns The regions.
 */
function readRegions(name: string) {
  return buildWorkspaceRegions(
    toTicketWorkspace(readOperationExample("getConsoleTicket", 200, name)),
  );
}

describe("buildWorkspaceRegions", () => {
  it("numbers the cited source and keeps the warnings of a ready draft", () => {
    const regions = readRegions("draft-ready");

    expect(regions.sources).toMatchObject([{ documentId: "SAMPLE-REFUND-001", number: 1 }]);
    expect(regions.warnings).toMatchObject([{ warningId: "w1" }]);
    expect(regions.generatedAt).toBe("2026-11-05T08:12:30Z");
  });

  it("lists the sources of an abstention without numbers", () => {
    expect(readRegions("abstained-low-confidence").sources).toMatchObject([
      { documentId: "SAMPLE-REFUND-001" },
    ]);
    expect(readRegions("abstained-low-confidence").numberByKey.size).toBe(0);
  });

  it("has no sources, warnings, or suggestion time in manual mode", () => {
    const regions = readRegions("manual-mode");

    expect(regions.sources).toEqual([]);
    expect(regions.warnings).toEqual([]);
    expect(regions.generatedAt).toBe(
      readOperationExample("getConsoleTicket", 200, "manual-mode").created_at,
    );
  });
});
