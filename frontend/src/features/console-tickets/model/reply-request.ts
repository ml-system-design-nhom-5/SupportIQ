/**
 * The bodies that Send reply and Submit for approval send (console UI design, Actions): the
 * `basis` follows from what staff did, and a reply on the AI draft names only the warnings that
 * staff acknowledged, so `422` stays the backstop of UI-18. A manager sends a proposal with the
 * basis `reply_proposal`. `backend` checks every rule again and refuses with `403`, `409`, or
 * `422` (FR-04, FR-06, SEC-38). Nothing here sends: only a staff click sends.
 */
import type {
  CreateReplyProposalRequestContract,
  SendReplyRequestContract,
} from "@/features/console-tickets/api/contract-types";
import {
  type ComposerDraft,
  type ComposerTicket,
  getReplyBody,
} from "@/features/console-tickets/model/composer-ticket";
import type { ComposerState } from "@/features/console-tickets/model/reply-composer";
import { staffReasonCodes } from "@/features/console-tickets/model/staff-reason-codes";

/** The ready AI draft that a reply or a proposal is based on. */
type AiDraft = Extract<ComposerDraft, { readonly kind: "ai_draft" }>;

/**
 * Build the body of `sendReply`: the basis `reply_proposal` with the proposal for a manager on a
 * ticket awaiting approval, and the basis of {@link buildReplyProposalRequest} otherwise.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The request body.
 */
export function buildSendReplyRequest(
  ticket: ComposerTicket,
  state: ComposerState,
): SendReplyRequestContract {
  const draft = ticket.draft;
  if (draft?.kind === "reply_proposal") {
    return {
      basis: "reply_proposal",
      body: getReplyBody(ticket, state),
      proposal_id: draft.proposalId,
    };
  }
  return buildReplyProposalRequest(ticket, state);
}

/**
 * Build the body of `createReplyProposal`, with the basis of the console UI design (Actions):
 * `ai_draft` for a ready draft sent as is or edited, with the warnings that staff acknowledged;
 * `rejected_ai_draft` with the chosen reason codes; `no_ai_draft` without a ready draft.
 *
 * @param ticket - The ticket.
 * @param state - What staff composed.
 * @returns The request body, which is also the body of `sendReply` on an open ticket.
 */
export function buildReplyProposalRequest(
  ticket: ComposerTicket,
  state: ComposerState,
): CreateReplyProposalRequestContract {
  const body = getReplyBody(ticket, state);
  const draft = ticket.draft?.kind === "ai_draft" ? ticket.draft : undefined;
  if (draft === undefined) {
    return {
      basis: "no_ai_draft",
      body,
      ...(ticket.suggestionId === undefined ? {} : { suggestion_id: ticket.suggestionId }),
    };
  }
  return state.draftMode === "rejecting"
    ? buildRejectedDraftReply(draft, state, body)
    : {
        basis: "ai_draft",
        body,
        suggestion_id: draft.suggestionId,
        acknowledged_warning_ids: ticket.warningIds.filter((warningId) =>
          state.acknowledgedWarningIds.has(warningId),
        ),
      };
}

/**
 * Build a reply after a rejection (ADR-0006): the reason codes in the order of the contract, and
 * the note only with `other`.
 *
 * @param draft - The rejected draft.
 * @param state - What staff composed.
 * @param body - The reply text.
 * @returns The request body.
 */
function buildRejectedDraftReply(
  draft: AiDraft,
  state: ComposerState,
  body: string,
): CreateReplyProposalRequestContract {
  return {
    basis: "rejected_ai_draft",
    body,
    suggestion_id: draft.suggestionId,
    staff_reason_codes: staffReasonCodes.filter((code) => state.reasonCodes.has(code)),
    ...(state.reasonCodes.has("other") ? { note: state.note } : {}),
  };
}
