/**
 * The reply area of one opened ticket (console UI design, Actions and Dialogs): what staff
 * composed, the confirmation step of Send reply (UI-17), and the send. Only a confirmation sends a
 * reply (FR-04). The state lives as long as the ticket is open, so a reload of the workspace keeps
 * the text that staff typed; it is never written to browser storage, because it is Confidential.
 */
import { useState } from "react";

import { getRequestFailure, useCreateIdempotencyKey } from "@/features/backend-requests";
import { useSendReply } from "@/features/console-tickets/api/use-send-reply";
import {
  type ComposerState,
  initialComposerState,
} from "@/features/console-tickets/model/reply-composer";
import {
  buildSendReplyRequest,
  canChangeDraft,
  type ComposerMode,
  type ComposerTicket,
  findSendBlock,
  getComposerMode,
  getReplyBody,
  isSameReply,
} from "@/features/console-tickets/model/reply-request";
import {
  describeSendFailure,
  type SendFailureView,
} from "@/features/console-tickets/model/send-failure";

/** The reply area of the opened ticket. */
export type ReplyComposer = {
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
  /** The button that opened the confirmation, while it is open. */
  readonly confirmationOpener: HTMLElement | undefined;
  /** Opens the confirmation (Send reply). */
  readonly askToSend: (opener: HTMLElement) => void;
  /** Closes the confirmation without a send (Keep editing). */
  readonly cancelSend: () => void;
  /** Sends the reply (the confirmation's Send reply). */
  readonly confirmSend: () => void;
  readonly isSending: boolean;
  /** The last failed send, in plain language; undefined after a success or before any send. */
  readonly sendFailure: SendFailureView | undefined;
};

/**
 * Keep the reply area of a ticket.
 *
 * @param ticketId - The ticket.
 * @param ticket - What the composer reads of the ticket.
 * @returns The state, its change, the send block, and the confirmation and send handlers.
 */
export function useReplyComposer(ticketId: string, ticket: ComposerTicket): ReplyComposer {
  const [state, setState] = useState(initialComposerState);
  const [confirmationOpener, setConfirmationOpener] = useState<HTMLElement | undefined>(undefined);
  const sendReply = useSendReply(ticketId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  const failure = getRequestFailure(sendReply.error);
  const confirmSend = () => {
    const request = buildSendReplyRequest(ticket, state);
    const failedReply = sendReply.isError ? sendReply.variables : undefined;
    const idempotencyKey =
      failedReply !== undefined && isSameReply(failedReply.request, request)
        ? failedReply.idempotencyKey
        : createIdempotencyKey();
    sendReply.mutate(
      { request, idempotencyKey },
      {
        onSettled: () => {
          setConfirmationOpener(undefined);
        },
      },
    );
  };
  return {
    state,
    mode: getComposerMode(ticket, state),
    canChangeDraft: canChangeDraft(ticket),
    change: setState,
    body: getReplyBody(ticket, state),
    sendBlock: findSendBlock(ticket, state),
    confirmationOpener,
    askToSend: setConfirmationOpener,
    cancelSend: () => {
      setConfirmationOpener(undefined);
    },
    confirmSend,
    isSending: sendReply.isPending,
    sendFailure: failure === undefined ? undefined : describeSendFailure(failure),
  };
}
