import { describe, expect, it } from "vitest";

import {
  STAFF_NOTE_MAX_LENGTH,
  staffReasonCodeLabels,
  staffReasonCodes,
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
