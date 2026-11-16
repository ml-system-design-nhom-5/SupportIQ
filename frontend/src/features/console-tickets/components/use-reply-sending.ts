/**
 * The confirmation step of Send reply (UI-17) and the send (console UI design, Actions and
 * Dialogs). Only a confirmation sends a reply (FR-04), and it sends exactly the reply that the
 * confirmation shows: the request and its `Idempotency-Key` are fixed when it opens. The
 * confirmation closes without a send when the suggestion or the proposal changes, or Send reply
 * becomes disabled, while it is open. Send reply is never retried automatically; confirming the
 * same reply again after a failure reuses its key (TS-29).
 */
import { useState } from "react";

import { useCreateIdempotencyKey } from "@/features/backend-requests";
import { chooseIdempotencyKey } from "@/features/console-tickets/api/keyed-writes";
import { type ConfirmedReply, useSendReply } from "@/features/console-tickets/api/use-send-reply";
import {
  type ComposerTicket,
  getComposedTextOwner,
} from "@/features/console-tickets/model/composer-ticket";
import type {
  ComposedTextOwner,
  ComposerState,
} from "@/features/console-tickets/model/reply-composer";
import {
  type DatedFailure,
  isTakenByColleague,
  readDatedFailure,
} from "@/features/console-tickets/model/reply-failure";
import { buildSendReplyRequest } from "@/features/console-tickets/model/reply-request";

/** The open confirmation: the button that opened it and the text that it sends. */
export type OpenConfirmation = {
  readonly opener: HTMLElement;
  /** The text that the customer receives. */
  readonly body: string;
};

/** The confirmation of Send reply and the send. */
export type ReplySending = {
  /** The confirmation while it is open. */
  readonly confirmation: OpenConfirmation | undefined;
  /** Opens the confirmation with the reply as it is now (Send reply). */
  readonly askToSend: (opener: HTMLElement) => void;
  /** Closes the confirmation without a send (Keep editing). */
  readonly cancelSend: () => void;
  /** Sends the reply that the confirmation shows (the confirmation's Send reply). */
  readonly confirmSend: () => void;
  readonly isSending: boolean;
  /** The last failed send, with when it was sent; undefined after a success. */
  readonly sendFailure: DatedFailure | undefined;
  /**
   * The text of a send that a colleague's action refused, until staff leave the ticket. It stays
   * in the memory of the mutation only, never in browser storage (console UI design, Flow, step 6).
   */
  readonly unsentText: string | undefined;
};

/** What the reply area does after a send. */
export type ReplySendingEvents = {
  readonly onSent: () => void;
  /** A colleague escalated the ticket or submitted it meanwhile, so the send was refused. */
  readonly onTakenByColleague: () => void;
};

/** What the send reads of the reply area now. */
export type ComposedReply = {
  readonly ticket: ComposerTicket;
  readonly state: ComposerState;
  /** Why Send reply is disabled; undefined while it is enabled. */
  readonly sendBlock: string | undefined;
};

/** A confirmation as the hook keeps it. */
type Confirmation = {
  readonly opener: HTMLElement;
  readonly reply: ConfirmedReply;
  /** The suggestion and the proposal that the reply was built on. */
  readonly owner: ComposedTextOwner;
};

/**
 * Keep the confirmation of Send reply and send the reply that it shows.
 *
 * @param ticketId - The ticket.
 * @param composed - The ticket, what staff composed, and the send block, as rendered now.
 * @param events - Called once a reply was sent, and once a colleague's action refused it.
 * @returns The open confirmation and its handlers, and the state of the send.
 */
export function useReplySending(
  ticketId: string,
  composed: ComposedReply,
  events: ReplySendingEvents,
): ReplySending {
  const [stored, setConfirmation] = useState<Confirmation | undefined>(undefined);
  const sendReply = useSendReply(ticketId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  const isStale = stored !== undefined && !sendReply.isPending && isOutdated(stored, composed);
  if (isStale) {
    setConfirmation(undefined);
  }
  const confirmation = isStale ? undefined : stored;
  const close = () => {
    setConfirmation(undefined);
  };
  return {
    confirmation: toOpenConfirmation(confirmation),
    askToSend: (opener) => {
      if (composed.sendBlock === undefined) {
        const request = buildSendReplyRequest(composed.ticket, composed.state);
        const idempotencyKey = chooseIdempotencyKey(request, sendReply, createIdempotencyKey);
        const owner = getComposedTextOwner(composed.ticket);
        setConfirmation({ opener, reply: { request, idempotencyKey }, owner });
      }
    },
    cancelSend: close,
    confirmSend: () => {
      if (confirmation !== undefined && !sendReply.isPending) {
        sendReply.mutate(confirmation.reply, toSendCallbacks(events, close));
      }
    },
    isSending: sendReply.isPending,
    sendFailure: readDatedFailure(sendReply, "send_reply"),
    unsentText: isTakenByColleague(sendReply.error) ? sendReply.variables?.request.body : undefined,
  };
}

/**
 * Choose what happens after one send.
 *
 * @param events - The events of the reply area.
 * @param close - Closes the confirmation.
 * @returns The callbacks of the mutation.
 */
function toSendCallbacks(events: ReplySendingEvents, close: () => void) {
  return {
    onSuccess: events.onSent,
    onError: (error: Error) => {
      if (isTakenByColleague(error)) {
        events.onTakenByColleague();
      }
    },
    onSettled: close,
  };
}

/**
 * Tell whether an open confirmation no longer shows what Send reply would send: a new suggestion
 * or proposal replaced the one that the reply was built on, or Send reply became disabled.
 *
 * @param confirmation - The open confirmation.
 * @param composed - The reply area as rendered now.
 * @returns True when the confirmation must close without a send.
 */
function isOutdated(confirmation: Confirmation, composed: ComposedReply): boolean {
  const owner = getComposedTextOwner(composed.ticket);
  return (
    confirmation.owner.suggestionId !== owner.suggestionId ||
    confirmation.owner.proposalId !== owner.proposalId ||
    composed.sendBlock !== undefined
  );
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
