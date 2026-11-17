import { describe, expect, it } from "vitest";

import {
  toAiReasonCode,
  toAiReasonCodes,
  toFirstReasonCode,
  toSuggestionWarning,
} from "@/features/console-tickets/model/reason-codes";
import { readContractSchema, readEnumValues } from "@/test/contract-schemas";

describe("toAiReasonCode", () => {
  it.each(readEnumValues(readContractSchema("AiReasonCode")))(
    "keeps the reason code %s of the contract",
    (code) => {
      expect(toAiReasonCode(code)).toBe(code);
    },
  );

  it("maps an unknown code to an unspecified reason (CON-22)", () => {
    expect(toAiReasonCode("budget_tripled")).toBe("unknown");
  });
});

describe("toAiReasonCodes", () => {
  it("keeps the order of backend and joins unknown codes into one", () => {
    expect(
      toAiReasonCodes(["requires_authority", "new_code", "low_confidence", "other_new_code"]),
    ).toEqual(["requires_authority", "unknown", "low_confidence"]);
  });

  it("returns no code for an empty list", () => {
    expect(toAiReasonCodes([])).toEqual([]);
  });
});

describe("toFirstReasonCode", () => {
  it.each([
    [["pseudonymization_failed"], "pseudonymization_failed"],
    [["not_a_code"], "unknown"],
    [[], "unknown"],
  ])("reads %j as %s", (codes, code) => {
    expect(toFirstReasonCode(codes)).toBe(code);
  });
});

describe("toSuggestionWarning", () => {
  it.each([
    [
      "source_review_overdue",
      "A source that the AI found is past its review date. Check that it still applies.",
    ],
    [
      "missing_information",
      "The request needs information that is in neither the message nor the order. See the note for staff.",
    ],
    ["grounding_failed", "Check the draft and its sources before you send it."],
  ])("says what to check for %s", (reasonCode, text) => {
    expect(toSuggestionWarning({ warning_id: "w1", reason_code: reasonCode })).toEqual({
      warningId: "w1",
      reasonCode,
      text,
    });
  });

  it("keeps a warning with an unknown code, so staff still acknowledge it (UI-18)", () => {
    expect(toSuggestionWarning({ warning_id: "w9", reason_code: "new_warning" })).toEqual({
      warningId: "w9",
      reasonCode: "unknown",
      text: "Check the draft and its sources before you send it.",
    });
  });
});
