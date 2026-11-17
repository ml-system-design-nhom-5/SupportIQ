import { describe, expect, it } from "vitest";

import {
  buildEscalationRequest,
  emptyEscalationForm,
  findEscalationErrors,
} from "@/features/console-tickets/model/escalation-form";
import { STAFF_NOTE_MAX_LENGTH } from "@/features/console-tickets/model/staff-reason-codes";
import { readOperationExample } from "@/test/contract-examples";

describe("findEscalationErrors (ADR-0006)", () => {
  it("asks for a reason before anything else is chosen", () => {
    expect(findEscalationErrors(emptyEscalationForm)).toEqual({
      reasons: "Choose at least one reason.",
    });
  });

  it.each([
    ["no note", "", "Write a note for the reason Other."],
    ["a note of spaces", "  ", "Write a note for the reason Other."],
  ])("asks for a note with the reason Other and %s", (_case, note, error) => {
    expect(findEscalationErrors({ reasonCodes: new Set(["other"]), note })).toEqual({
      note: error,
    });
  });

  it("asks to shorten a note over 1 000 characters, whatever the reason", () => {
    expect(
      findEscalationErrors({
        reasonCodes: new Set(["kb_gap"]),
        note: "n".repeat(STAFF_NOTE_MAX_LENGTH + 1),
      }),
    ).toEqual({ note: "Shorten the note to 1,000 characters." });
  });

  it("accepts a reason without a note, and Other with a note of 1 000 characters", () => {
    expect(findEscalationErrors({ reasonCodes: new Set(["kb_gap"]), note: "" })).toEqual({});
    expect(
      findEscalationErrors({
        reasonCodes: new Set(["other"]),
        note: "n".repeat(STAFF_NOTE_MAX_LENGTH),
      }),
    ).toEqual({});
  });
});

describe("buildEscalationRequest", () => {
  it("sends the reasons in the order of the contract, the note, and the suggestion", () => {
    expect(
      buildEscalationRequest(
        { reasonCodes: new Set(["other", "kb_gap"]), note: "The customer called." },
        "s1",
      ),
    ).toEqual({
      staff_reason_codes: ["kb_gap", "other"],
      note: "The customer called.",
      suggestion_id: "s1",
    });
  });

  it("sends no note when staff wrote none, and no suggestion in manual mode", () => {
    expect(
      buildEscalationRequest({ reasonCodes: new Set(["missing_case_info"]), note: " " }, undefined),
    ).toEqual({ staff_reason_codes: ["missing_case_info"] });
  });

  it("builds a body that the contract accepts, as its example does", () => {
    const example = readOperationExample("createEscalation", 201, "escalated");

    expect(
      buildEscalationRequest(
        { reasonCodes: new Set(example.staff_reason_codes), note: example.note ?? "" },
        example.suggestion_id,
      ),
    ).toMatchObject({ staff_reason_codes: example.staff_reason_codes });
  });
});
