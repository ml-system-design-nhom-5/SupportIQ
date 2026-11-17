import { describe, expect, it } from "vitest";

import {
  toAiStatus,
  toConfidenceBand,
  toHandlingMode,
  toTicketStatus,
} from "@/features/console-tickets/model/ticket-status";
import { readBackendSchema, readContractSchema, readEnumValues } from "@/test/contract-schemas";

describe("toTicketStatus", () => {
  it.each(readEnumValues(readBackendSchema("ConsoleTicketStatus")))(
    "keeps the status %s",
    (status) => {
      expect(toTicketStatus(status)).toBe(status);
    },
  );

  it("maps an unknown status to unknown, a state with no action (CON-22)", () => {
    expect(toTicketStatus("on_hold")).toBe("unknown");
  });
});

describe("toHandlingMode", () => {
  it.each([
    ["assisted", "assisted"],
    ["manual", "manual"],
    ["hybrid", "manual"],
  ])("maps %s to %s, as the contract says (CON-22)", (value, mode) => {
    expect(toHandlingMode(value)).toBe(mode);
  });
});

describe("toAiStatus", () => {
  it("knows every draft status of the contract", () => {
    expect(readEnumValues(readBackendSchema("DraftStatus")).map(toAiStatus)).toEqual([
      "pending",
      "draft_ready",
      "abstained",
      "escalation_recommended",
      "unavailable",
      "unavailable",
    ]);
  });

  it("maps an unknown draft status to unavailable, so the ticket is handled manually", () => {
    expect(toAiStatus("drafting_slowly")).toBe("unavailable");
  });
});

describe("toConfidenceBand", () => {
  it.each(readEnumValues(readContractSchema("ConfidenceBand")))("keeps the band %s", (band) => {
    expect(toConfidenceBand(band)).toBe(band);
  });

  it("maps an unknown band to low (CON-22)", () => {
    expect(toConfidenceBand("very_high")).toBe("low");
  });
});
