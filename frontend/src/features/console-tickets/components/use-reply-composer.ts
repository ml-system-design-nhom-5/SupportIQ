/**
 * The reply area of one opened ticket (console UI design, Actions and Dialogs): what staff
 * composed, the confirmation step of Send reply (UI-17), and the send. Only a confirmation sends a
 * reply (FR-04), and it sends exactly the reply that the confirmation shows: the request and its
 * `Idempotency-Key` are fixed when it opens. The confirmation closes without a send when the
 * suggestion changes or Send reply becomes disabled while it is open. The state lives as long as
 * the ticket is open, so a reload of the workspace keeps the text that staff typed; it is never
 * written to browser storage, because it is Confidential.
 */
import { useState } from "react";

import { getRequestFailure, useCreateIdempotencyKey } from "@/features/backend-requests";
import type { SendReplyRequestContract } from "@/features/console-tickets/api/contract-types";
import { type ConfirmedReply, useSendReply } from "@/features/console-tickets/api/use-send-reply";
import {
  type ComposerState,
  createComposerState,
  followSuggestion,
} from "@/features/console-tickets/model/reply-composer";
import {
  buildSendReplyRequest,
  canChangeDraft,
  type ComposerMode,
  type ComposerTicket,
  getComposerMode,
  getReplyBody,
  isSameReply,
} from "@/features/console-tickets/model/reply-request";
import { findSendBlock } from "@/features/console-tickets/model/send-block";
import {
  describeSendFailure,
  type SendFailureView,
} from "@/features/console-tickets/model/send-failure";

/** The open confirmation: the button that opened it and the text that it sends. */
export type OpenConfirmation = {
  readonly opener: HTMLElement;
  /** The text that the customer receives. */
  readonly body: string;
};

/** The confirmation of Send reply and the send. */
type ReplySending = {
  /** The confirmation while it is open. */
  readonly confirmation: OpenConfirmation | undefined;
  /** Opens the confirmation with the reply as it is now (Send reply). */
  readonly askToSend: (opener: HTMLElement) => void;
  /** Closes the confirmation without a send (Keep editing). */
  readonly cancelSend: () => void;
  /** Sends the reply that the confirmation shows (the confirmation's Send reply). */
  readonly confirmSend: () => void;
  readonly isSending: boolean;
  /** The last failed send, in plain language; undefined after a success or before any send. */
  readonly sendFailure: SendFailureView | undefined;
};

/** The reply area of the opened ticket. */
export type ReplyComposer = ReplySending & {
  /** What staff composed, for the current suggestion. */
  readonly state: ComposerState;
  /** What staff do: a mode of the ready draft, or `writing` without one. */
  readonly mode: ComposerMode;
  /** True when Edit draft and Reject draft are enabled. */
  readonly canChangeDraft: boolean;
  /** Changes what staff composed. */
  readonly change: (update: (state: ComposerState) => ComposerState) => void;
  /** The text that Send reply sends. */
  readonly body: string;
  /** Why Send reply is disabled; undefined when it is enabled. */
  readonly sendBlock: string | undefined;
};

/** What the send reads of the reply area now. */
type ComposedReply = {
  readonly ticket: ComposerTicket;
  readonly state: ComposerState;
  readonly sendBlock: string | undefined;
};

/** A confirmation as the composer keeps it. */
type Confirmation = {
  readonly opener: HTMLElement;
  readonly reply: ConfirmedReply;
  /** The suggestion that the reply was built on. */
  readonly suggestionId: string | undefined;
};

/**
 * Keep the reply area of a ticket.
 *
 * @param ticketId - The ticket of the address, the ticket of the send.
 * @param ticket - What the composer reads of the ticket.
 * @param onSent - Called once a reply was sent.
 * @returns The state, its change, the send block, and the confirmation and send handlers.
 */
export function useReplyComposer(
  ticketId: string,
  ticket: ComposerTicket,
  onSent: () => void,
): ReplyComposer {
  const [storedState, setState] = useState(() => createComposerState(ticket.suggestionId));
  // A new suggestion resets what belonged to the old one, during the render that shows it (TS-21).
  const state = followSuggestion(storedState, ticket.suggestionId);
  if (state !== storedState) {
    setState(state);
  }
  const sendBlock = findSendBlock(ticket, state);
  return {
    state,
    mode: getComposerMode(ticket, state),
    canChangeDraft: canChangeDraft(ticket),
    change: setState,
    body: getReplyBody(ticket, state),
    sendBlock,
    ...useReplySending(ticketId, { ticket, state, sendBlock }, onSent),
  };
}

/**
 * Keep the confirmation of Send reply and send the reply that it shows. Send reply is never retried
 * automatically; confirming the same reply again after a failure reuses its key (TS-29).
 *
 * @param ticketId - The ticket.
 * @param composed - The ticket, what staff composed, and the send block, as rendered now.
 * @param onSent - Called once a reply was sent.
 * @returns The open confirmation and its handlers, and the state of the send.
 */
function useReplySending(
  ticketId: string,
  composed: ComposedReply,
  onSent: () => void,
): ReplySending {
  const [stored, setConfirmation] = useState<Confirmation | undefined>(undefined);
  const sendReply = useSendReply(ticketId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  const isStale = stored !== undefined && !sendReply.isPending && isOutdated(stored, composed);
  if (isStale) {
    setConfirmation(undefined);
  }
  const confirmation = isStale ? undefined : stored;
  const failure = getRequestFailure(sendReply.error);
  const failedReply = sendReply.isError ? sendReply.variables : undefined;
  const close = () => {
    setConfirmation(undefined);
  };
  return {
    confirmation: toOpenConfirmation(confirmation),
    askToSend: (opener) => {
      if (composed.sendBlock === undefined) {
        setConfirmation(
          prepareConfirmation(composed, opener, (request) =>
            chooseKey(request, failedReply, createIdempotencyKey),
          ),
        );
      }
    },
    cancelSend: close,
    confirmSend: () => {
      if (confirmation !== undefined && !sendReply.isPending) {
        sendReply.mutate(confirmation.reply, { onSuccess: onSent, onSettled: close });
      }
    },
    isSending: sendReply.isPending,
    sendFailure: failure === undefined ? undefined : describeSendFailure(failure),
  };
}

/**
 * Tell whether an open confirmation no longer shows what Send reply would send: a new suggestion
 * replaced the one that the reply was built on, or Send reply became disabled.
 *
 * @param confirmation - The open confirmation.
 * @param composed - The reply area as rendered now.
 * @returns True when the confirmation must close without a send.
 */
function isOutdated(confirmation: Confirmation, composed: ComposedReply): boolean {
  return (
    confirmation.suggestionId !== composed.ticket.suggestionId || composed.sendBlock !== undefined
  );
}

/**
 * Choose the `Idempotency-Key` of a confirmation: the key of the failed send when staff confirm the
 * same reply again, so a reply whose outcome was unknown reaches the customer once; a new key for
 * any other reply.
 *
 * @param request - The reply that the confirmation shows.
 * @param failedReply - The reply of the last send when it failed.
 * @param createIdempotencyKey - Creates a new key.
 * @returns The key.
 */
function chooseKey(
  request: SendReplyRequestContract,
  failedReply: ConfirmedReply | undefined,
  createIdempotencyKey: () => string,
): string {
  return failedReply !== undefined && isSameReply(failedReply.request, request)
    ? failedReply.idempotencyKey
    : createIdempotencyKey();
}

/**
 * Fix the reply of a confirmation as it is now, with its key.
 *
 * @param composed - The reply area as rendered now.
 * @param opener - The Send reply button.
 * @param keyOf - Gives the `Idempotency-Key` of the reply.
 * @returns The confirmation.
 */
function prepareConfirmation(
  composed: ComposedReply,
  opener: HTMLElement,
  keyOf: (request: SendReplyRequestContract) => string,
): Confirmation {
  const request = buildSendReplyRequest(composed.ticket, composed.state);
  return {
    opener,
    reply: { request, idempotencyKey: keyOf(request) },
    suggestionId: composed.ticket.suggestionId,
  };
}

/**
 * Show a confirmation: its opener and the text that it sends.
 *
 * @param confirmation - The open confirmation, or undefined.
 * @returns What the dialog shows, or undefined while it is closed.
 */
function toOpenConfirmation(confirmation: Confirmation | undefined): OpenConfirmation | undefined {
  return confirmation === undefined
    ? undefined
    : { opener: confirmation.opener, body: confirmation.reply.request.body };
}
