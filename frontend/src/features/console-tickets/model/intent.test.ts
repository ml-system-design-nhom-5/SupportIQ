import { describe, expect, it } from "vitest";

import { intentLabels, toIntent } from "@/features/console-tickets/model/intent";
import { readContractSchema, readEnumValues } from "@/test/contract-schemas";

describe("intentLabels", () => {
  it("lists the 46 labels of IntentLabel in the contract", () => {
    expect(intentLabels).toEqual(readEnumValues(readContractSchema("IntentLabel")));
  });
});

describe("toIntent", () => {
  it.each([
    ["refund_status", "Refund status"],
    ["human_agent", "Human agent"],
    ["pay", "Pay"],
    ["request_right_to_rectification", "Request right to rectification"],
  ])("names %s %s", (label, name) => {
    expect(toIntent(label)).toEqual({ label, name });
  });

  it.each(["gift_wrap", "", "Refund_Status"])(
    "maps the unknown label %j to an unspecified intent (CON-22)",
    (label) => {
      expect(toIntent(label)).toEqual({ label: "unknown", name: "Unspecified intent" });
    },
  );
});
