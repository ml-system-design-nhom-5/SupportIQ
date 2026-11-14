/**
 * The form of Escalate ticket (console UI design, Dialogs; ADR-0006): at least one staff reason
 * code, and a note, required with `other`. The dialog checks it when staff press Escalate ticket;
 * `backend` checks it again and refuses with `422`.
 */
import { countContractCharacters } from "@/features/backend-requests";
import type { CreateEscalationRequestContract } from "@/features/console-tickets/api/contract-types";
import {
  STAFF_NOTE_MAX_LENGTH,
  type StaffReasonCode,
  staffReasonCodes,
} from "@/features/console-tickets/model/staff-reason-codes";

/** What staff chose in the dialog. */
export type EscalationForm = {
  readonly reasonCodes: ReadonlySet<StaffReasonCode>;
  /** The note; empty when staff wrote none. */
  readonly note: string;
};

/** What the form still needs, next to each field; empty when it can be sent. */
export type EscalationErrors = {
  readonly reasons?: string;
  readonly note?: string;
};

/** The form when the dialog opens: no reason chosen and no note. */
export const emptyEscalationForm: EscalationForm = { reasonCodes: new Set(), note: "" };

/**
 * Check the form.
 *
 * @param form - What staff chose.
 * @returns A message for the reasons when none is chosen, and one for the note when `other` has
 *   none or the note is longer than 1 000 characters.
 */
export function findEscalationErrors(form: EscalationForm): EscalationErrors {
  const noteError = findNoteError(form);
  return {
    ...(form.reasonCodes.size === 0 ? { reasons: "Choose at least one reason." } : {}),
    ...(noteError === undefined ? {} : { note: noteError }),
  };
}

/**
 * Build the body of `createEscalation`.
 *
 * @param form - A form without errors.
 * @param suggestionId - The current suggestion that staff saw; undefined without one.
 * @returns The reason codes in the order of the contract, the note when staff wrote one, and the
 *   suggestion.
 */
export function buildEscalationRequest(
  form: EscalationForm,
  suggestionId: string | undefined,
): CreateEscalationRequestContract {
  return {
    staff_reason_codes: staffReasonCodes.filter((code) => form.reasonCodes.has(code)),
    ...(form.note.trim() === "" ? {} : { note: form.note }),
    ...(suggestionId === undefined ? {} : { suggestion_id: suggestionId }),
  };
}

/**
 * Check the note.
 *
 * @param form - What staff chose.
 * @returns The message, or undefined when the note may be sent.
 */
function findNoteError(form: EscalationForm): string | undefined {
  if (form.reasonCodes.has("other") && form.note.trim() === "") {
    return "Write a note for the reason Other.";
  }
  return countContractCharacters(form.note) > STAFF_NOTE_MAX_LENGTH
    ? "Shorten the note to 1,000 characters."
    : undefined;
}
