/**
 * The staff reason codes (ADR-0006; console UI design, state-rejected.png): why staff rejected a
 * draft. They are business terms, never ML jargon (UI-28). `other` needs a note.
 */
import type { StaffReasonCodeContract } from "@/features/console-tickets/api/contract-types";

/** The reason codes of the contract, in its order, which is the order of the chips. */
export const staffReasonCodes = [
  "wrong_intent",
  "wrong_source",
  "unsupported_claim",
  "kb_gap",
  "missing_case_info",
  "tone_or_clarity",
  "case_exception",
  "other",
] as const satisfies readonly StaffReasonCodeContract[];

/** A staff reason code. */
export type StaffReasonCode = (typeof staffReasonCodes)[number];

/** The `maxLength` of `StaffNoteText`: a note has from 1 to 1 000 characters. */
export const STAFF_NOTE_MAX_LENGTH = 1000;

/** The chip label of each reason code. */
export const staffReasonCodeLabels: Readonly<Record<StaffReasonCode, string>> = {
  wrong_intent: "Wrong intent",
  wrong_source: "Wrong source",
  unsupported_claim: "Unsupported claim",
  kb_gap: "KB gap",
  missing_case_info: "Missing case info",
  tone_or_clarity: "Tone or clarity",
  case_exception: "Case exception",
  other: "Other",
};

/**
 * Map staff reason codes of `backend`, in the order of the contract.
 *
 * @param values - The `staff_reason_codes` of a proposal or an escalation.
 * @returns The codes; a value that this version does not know is ignored (CON-22).
 */
export function toStaffReasonCodes(values: readonly string[]): readonly StaffReasonCode[] {
  const given: ReadonlySet<string> = new Set(values);
  return staffReasonCodes.filter((code) => given.has(code));
}

/** The chips of the staff reason codes, in the order of the contract. */
export const staffReasonOptions: readonly {
  readonly value: StaffReasonCode;
  readonly label: string;
}[] = staffReasonCodes.map((code) => ({ value: code, label: staffReasonCodeLabels[code] }));

/**
 * Choose or unchoose a reason code.
 *
 * @param codes - The chosen codes.
 * @param reasonCode - The chip that staff pressed.
 * @returns The codes with it added, or removed when it was chosen.
 */
export function toggleStaffReasonCode(
  codes: ReadonlySet<StaffReasonCode>,
  reasonCode: StaffReasonCode,
): ReadonlySet<StaffReasonCode> {
  const toggled = new Set(codes);
  if (!toggled.delete(reasonCode)) {
    toggled.add(reasonCode);
  }
  return toggled;
}
