import { describe, expect, it } from "vitest";

import {
  shownStaffReasonCodeLabels,
  STAFF_NOTE_MAX_LENGTH,
  staffReasonCodeLabels,
  staffReasonCodes,
  staffReasonOptions,
  toggleStaffReasonCode,
  toStaffReasonCodes,
} from "@/features/console-tickets/model/staff-reason-codes";
import { readBackendSchema, readEnumValues } from "@/test/contract-schemas";

describe("staffReasonCodes", () => {
  it("lists the values of StaffReasonCode in the contract, in its order", () => {
    expect(staffReasonCodes).toEqual(readEnumValues(readBackendSchema("StaffReasonCode")));
  });

  it("labels each code as the rejected-draft mockup does", () => {
    expect(staffReasonCodeLabels).toEqual({
      wrong_intent: "Wrong intent",
      wrong_source: "Wrong source",
      unsupported_claim: "Unsupported claim",
      kb_gap: "KB gap",
      missing_case_info: "Missing case info",
      tone_or_clarity: "Tone or clarity",
      case_exception: "Case exception",
      other: "Other",
    });
  });
});

describe("STAFF_NOTE_MAX_LENGTH", () => {
  it("is the maxLength of StaffNoteText in the contract", () => {
    expect(readBackendSchema("StaffNoteText")).toContain(
      `maxLength: ${String(STAFF_NOTE_MAX_LENGTH)}\n`,
    );
  });
});

describe("staffReasonOptions", () => {
  it("gives each code its label, in the order of the contract", () => {
    expect(staffReasonOptions.map((option) => option.value)).toEqual(staffReasonCodes);
    expect(staffReasonOptions[0]).toEqual({ value: "wrong_intent", label: "Wrong intent" });
  });
});

describe("toStaffReasonCodes", () => {
  it("orders the codes as the contract does, and shows unknown values once as unknown (CON-22)", () => {
    expect(toStaffReasonCodes(["kb_gap", "new_code", "wrong_intent", "other_new"])).toEqual([
      "wrong_intent",
      "kb_gap",
      "unknown",
    ]);
    expect(shownStaffReasonCodeLabels.unknown).toBe("Unspecified reason");
  });
});

describe("toggleStaffReasonCode", () => {
  it("adds a code, and removes it when pressed again", () => {
    const chosen = toggleStaffReasonCode(new Set(), "other");

    expect(chosen).toEqual(new Set(["other"]));
    expect(toggleStaffReasonCode(chosen, "other")).toEqual(new Set());
  });
});
