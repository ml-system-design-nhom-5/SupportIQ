/**
 * The staff reason codes (ADR-0006; console UI design, state-rejected.png, dialog-escalate.png):
 * why staff rejected a draft or escalated a ticket. They are business terms, never ML jargon
 * (UI-28). `other` needs a note, and every note follows the rule of `StaffNoteText`.
 */
import { formatCount, type ToggleChipOption } from "@/design-system";
import { countContractCharacters } from "@/features/backend-requests";
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

/** The label of each shown reason code. */
export const shownStaffReasonCodeLabels: Readonly<Record<ShownStaffReasonCode, string>> = {
  ...staffReasonCodeLabels,
  unknown: "Unspecified reason",
};

/** The chips of the staff reason codes, in the order of the contract. */
export const staffReasonOptions: readonly ToggleChipOption<StaffReasonCode>[] =
  staffReasonCodes.map((code) => ({ value: code, label: staffReasonCodeLabels[code] }));

const knownStaffReasonCodes: ReadonlySet<string> = new Set(staffReasonCodes);

/** A staff reason code. */
export type StaffReasonCode = (typeof staffReasonCodes)[number];

/**
 * A staff reason code as the console shows it: `unknown` for a code that this version does not
 * know (CON-22).
 */
export type ShownStaffReasonCode = StaffReasonCode | "unknown";

/**
 * What a staff note still needs (`StaffNoteText`, ADR-0006).
 * `missing`: the reason code `other` needs a note, and there is none.
 * `too_long`: the note has more than 1 000 characters.
 */
export type StaffNoteProblem = "missing" | "too_long";

/**
 * Map one staff reason code of `backend`, such as the code of one count of a report.
 *
 * @param value - A `StaffReasonCode`.
 * @returns The code, or `unknown` for a code that this version does not know (CON-22).
 */
export function toStaffReasonCode(value: string): ShownStaffReasonCode {
  return isStaffReasonCode(value) ? value : "unknown";
}

/**
 * Map staff reason codes of `backend`, in the order of the contract.
 *
 * @param values - The `staff_reason_codes` of an escalation.
 * @returns The codes; codes that this version does not know show once, as `unknown`, at the end.
 */
export function toStaffReasonCodes(values: readonly string[]): readonly ShownStaffReasonCode[] {
  const given: ReadonlySet<string> = new Set(values);
  const known = staffReasonCodes.filter((code) => given.has(code));
  return values.some((value) => !knownStaffReasonCodes.has(value)) ? [...known, "unknown"] : known;
}

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

/**
 * Check a staff note, the same way for a rejection and for an escalation.
 *
 * @param note - The note as typed.
 * @param isRequired - True when the reason code `other` is chosen.
 * @returns The problem, or undefined when the note may be sent.
 */
export function findStaffNoteProblem(
  note: string,
  isRequired: boolean,
): StaffNoteProblem | undefined {
  if (isRequired && note.trim() === "") {
    return "missing";
  }
  return countContractCharacters(note) > STAFF_NOTE_MAX_LENGTH ? "too_long" : undefined;
}

/**
 * Describe what a staff note still needs.
 *
 * @param problem - What the note still needs.
 * @param goal - What the note allows, such as "to send the reply"; absent next to the field.
 * @returns The sentence, such as "Write a note for the reason Other to send the reply.".
 */
export function describeStaffNoteProblem(problem: StaffNoteProblem, goal?: string): string {
  const need =
    problem === "missing"
      ? "Write a note for the reason Other"
      : `Shorten the note to ${formatCount(STAFF_NOTE_MAX_LENGTH)} characters`;
  return goal === undefined ? `${need}.` : `${need} ${goal}.`;
}

/**
 * Tell whether a value is a staff reason code that this version knows.
 *
 * @param value - A `StaffReasonCode` from `backend`.
 * @returns True for a code of the contract.
 */
function isStaffReasonCode(value: string): value is StaffReasonCode {
  return knownStaffReasonCodes.has(value);
}
