/**
 * What staff do in the reply area before Send reply (console UI design, Actions and Draft editing):
 * read the draft, edit it, or reject it with reason codes and write another reply; or write a reply
 * when there is no ready draft. The state lives with the open ticket, so a reload of the workspace
 * keeps the text that staff typed; it is never written to browser storage, because it is
 * Confidential.
 */
import type { StaffReasonCode } from "@/features/console-tickets/model/staff-reason-codes";

/**
 * What staff do with a ready draft.
 * `viewing`: they read it, and Send reply sends it as is.
 * `editing`: its canonical `text` is in the editor.
 * `rejecting`: they rejected it; the editor starts empty.
 */
export type DraftMode = "viewing" | "editing" | "rejecting";

/** What staff composed so far. */
export type ComposerState = {
  readonly draftMode: DraftMode;
  /** The text of the editor: the edited draft, the reply after a rejection, or a reply without a draft. */
  readonly body: string;
  readonly reasonCodes: ReadonlySet<StaffReasonCode>;
  /** The note that the reason code `other` needs; empty when there is none. */
  readonly note: string;
  readonly acknowledgedWarningIds: ReadonlySet<string>;
};

/** The state when a ticket opens: the draft is read as is, and nothing is typed yet. */
export const initialComposerState: ComposerState = {
  draftMode: "viewing",
  body: "",
  reasonCodes: new Set(),
  note: "",
  acknowledgedWarningIds: new Set(),
};

/**
 * Put the draft's canonical `text` in the editor (Edit draft). `frontend` never rebuilds the text
 * from segments, so a draft sent unchanged is recorded as approved.
 *
 * @param state - The state.
 * @param draftText - The `text` of the ready draft.
 * @returns The state with the draft in the editor.
 */
export function startEditing(state: ComposerState, draftText: string): ComposerState {
  return { ...state, draftMode: "editing", body: draftText };
}

/**
 * Leave the editor and read the draft again (Discard edits).
 *
 * @param state - The state.
 * @returns The state with the draft read as is.
 */
export function discardEdits(state: ComposerState): ComposerState {
  return { ...state, draftMode: "viewing", body: "" };
}

/**
 * Reject the draft (Reject draft): the editor starts empty, and no reason is chosen yet.
 *
 * @param state - The state.
 * @returns The state of a rejected draft.
 */
export function rejectDraft(state: ComposerState): ComposerState {
  return { ...state, draftMode: "rejecting", body: "", reasonCodes: new Set(), note: "" };
}

/**
 * Choose or unchoose a reason code of the rejection.
 *
 * @param state - The state.
 * @param reasonCode - The chip that staff pressed.
 * @returns The state with the code added or removed.
 */
export function toggleReasonCode(state: ComposerState, reasonCode: StaffReasonCode): ComposerState {
  const reasonCodes = new Set(state.reasonCodes);
  if (!reasonCodes.delete(reasonCode)) {
    reasonCodes.add(reasonCode);
  }
  return { ...state, reasonCodes };
}

/**
 * Acknowledge a warning, or take the acknowledgement back (UI-18).
 *
 * @param state - The state.
 * @param warning - The `warning_id` and whether staff checked it.
 * @returns The state with the acknowledgement changed.
 */
export function acknowledgeWarning(
  state: ComposerState,
  warning: { readonly warningId: string; readonly isAcknowledged: boolean },
): ComposerState {
  const acknowledgedWarningIds = new Set(state.acknowledgedWarningIds);
  if (warning.isAcknowledged) {
    acknowledgedWarningIds.add(warning.warningId);
  } else {
    acknowledgedWarningIds.delete(warning.warningId);
  }
  return { ...state, acknowledgedWarningIds };
}
