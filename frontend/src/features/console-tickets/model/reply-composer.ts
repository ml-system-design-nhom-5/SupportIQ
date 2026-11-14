/**
 * What staff do in the reply area before Send reply (console UI design, Actions and Draft editing):
 * read the draft, edit it, or reject it with reason codes and write another reply; or write a reply
 * when there is no ready draft. The state lives with the open ticket, so a reload of the workspace
 * keeps the text that staff typed; it is never written to browser storage, because it is
 * Confidential.
 *
 * The acknowledgements and the reasons of a rejection belong to one suggestion. When a new
 * suggestion replaces it, they are dropped, so nothing that staff checked on the old one counts for
 * the new one (UI-18, ADR-0006). The text that staff typed stays in the editor, and the new draft
 * shows above it (console UI design, Errors and guardrails, "The draft was superseded").
 */
import {
  type StaffReasonCode,
  toggleStaffReasonCode,
} from "@/features/console-tickets/model/staff-reason-codes";

/**
 * What staff do with a ready draft.
 * `viewing`: they read it, and Send reply sends it as is.
 * `editing`: its canonical `text` is in the editor.
 * `rejecting`: they rejected it; the editor starts empty.
 * `keeping`: a new draft replaced the one that staff worked on; their text stays in the editor,
 * under the new draft, and Send reply sends it as an edit of the new draft.
 */
export type DraftMode = "viewing" | "editing" | "rejecting" | "keeping";

/**
 * Where the text in the editor came from while staff keep it over a new draft.
 * `edited_draft`: an edit of the previous draft.
 * `own_reply`: a reply that staff wrote after a rejection, or while there was no draft.
 */
export type KeptTextOrigin = "edited_draft" | "own_reply";

/** What staff composed so far. */
export type ComposerState = {
  /** The suggestion that the acknowledgements and the reasons belong to; absent in `manual` mode. */
  readonly suggestionId: string | undefined;
  readonly draftMode: DraftMode;
  /** The text of the editor: the edited draft, the reply after a rejection, or a reply without a draft. */
  readonly body: string;
  /** Where the kept text came from; set only in the mode `keeping`. */
  readonly keptTextOrigin: KeptTextOrigin | undefined;
  readonly reasonCodes: ReadonlySet<StaffReasonCode>;
  /** The note that the reason code `other` needs; empty when there is none. */
  readonly note: string;
  readonly acknowledgedWarningIds: ReadonlySet<string>;
};

/**
 * Create the state of a ticket that opens: the draft is read as is, and nothing is typed yet.
 *
 * @param suggestionId - The current suggestion of the ticket; undefined in `manual` mode.
 * @returns The state.
 */
export function createComposerState(suggestionId: string | undefined): ComposerState {
  return {
    suggestionId,
    draftMode: "viewing",
    body: "",
    keptTextOrigin: undefined,
    reasonCodes: new Set(),
    note: "",
    acknowledgedWarningIds: new Set(),
  };
}

/**
 * Keep the state with the current suggestion. When a new suggestion replaced the one that staff
 * worked on, after an intent correction, Try AI again, or a reload after `409
 * suggestion-superseded`, its acknowledgements, reason codes, and note are dropped. Text that staff
 * typed stays in the editor, under the new draft; without text, staff read the new draft as is.
 *
 * @param state - The state.
 * @param suggestionId - The current suggestion of the ticket.
 * @returns The same state while the suggestion is the same; the state for the new one otherwise.
 */
export function followSuggestion(
  state: ComposerState,
  suggestionId: string | undefined,
): ComposerState {
  if (state.suggestionId === suggestionId) {
    return state;
  }
  const replaced = createComposerState(suggestionId);
  return state.body.trim() === ""
    ? replaced
    : {
        ...replaced,
        draftMode: "keeping",
        body: state.body,
        keptTextOrigin: findKeptTextOrigin(state),
      };
}

/**
 * Put the draft's canonical `text` in the editor (Edit draft). `frontend` never rebuilds the text
 * from segments, so a draft sent unchanged is recorded as approved.
 *
 * @param state - The state.
 * @param draftText - The `text` of the ready draft.
 * @returns The state with the draft in the editor.
 */
export function startEditing(state: ComposerState, draftText: string): ComposerState {
  return { ...state, draftMode: "editing", body: draftText, keptTextOrigin: undefined };
}

/**
 * Leave the editor and read the draft again (Discard edits).
 *
 * @param state - The state.
 * @returns The state with the draft read as is.
 */
export function discardEdits(state: ComposerState): ComposerState {
  return { ...state, draftMode: "viewing", body: "", keptTextOrigin: undefined };
}

/**
 * Reject the draft (Reject draft), with no reason chosen yet. The editor starts empty, except that
 * text staff kept over a new draft stays.
 *
 * @param state - The state.
 * @returns The state of a rejected draft.
 */
export function rejectDraft(state: ComposerState): ComposerState {
  return {
    ...state,
    draftMode: "rejecting",
    body: state.draftMode === "keeping" ? state.body : "",
    keptTextOrigin: undefined,
    reasonCodes: new Set(),
    note: "",
  };
}

/**
 * Choose or unchoose a reason code of the rejection.
 *
 * @param state - The state.
 * @param reasonCode - The chip that staff pressed.
 * @returns The state with the code added or removed.
 */
export function toggleReasonCode(state: ComposerState, reasonCode: StaffReasonCode): ComposerState {
  return { ...state, reasonCodes: toggleStaffReasonCode(state.reasonCodes, reasonCode) };
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

/**
 * Tell where the text in the editor came from, when a new draft replaces the one staff worked on.
 *
 * @param state - The state before the new suggestion.
 * @returns `edited_draft` for an edit of the previous draft, also when it was kept over an earlier
 *   new draft; `own_reply` for a reply that staff wrote themselves.
 */
function findKeptTextOrigin(state: ComposerState): KeptTextOrigin {
  if (state.keptTextOrigin !== undefined) {
    return state.keptTextOrigin;
  }
  return state.draftMode === "editing" ? "edited_draft" : "own_reply";
}
