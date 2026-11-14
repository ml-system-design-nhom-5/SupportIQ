/**
 * Escalate ticket of the reply area (console UI design, Actions and Dialogs; ADR-0006): the button
 * opens a dialog with the staff reason codes and a note, and the dialog's Escalate ticket sends
 * `createEscalation`. The AI only recommends an escalation; only this staff action decides it. The
 * form is checked when staff press Escalate ticket, and then again with every change. The request
 * is built at that press, with the current suggestion, because staff may escalate while a
 * suggestion part is `pending`.
 */
import { useState } from "react";

import { getRequestFailure, useCreateIdempotencyKey } from "@/features/backend-requests";
import type { CreateEscalationRequestContract } from "@/features/console-tickets/api/contract-types";
import {
  type RequestedEscalation,
  useCreateEscalation,
} from "@/features/console-tickets/api/use-create-escalation";
import type { ComposerTicket } from "@/features/console-tickets/model/composer-ticket";
import {
  buildEscalationRequest,
  emptyEscalationForm,
  type EscalationErrors,
  type EscalationForm,
  findEscalationErrors,
} from "@/features/console-tickets/model/escalation-form";
import type { FailureView } from "@/features/console-tickets/model/failure-view";
import { describeReplyFailure } from "@/features/console-tickets/model/send-failure";

/** The open dialog. */
export type EscalationDialogState = {
  /** The Escalate ticket button that opened it. */
  readonly opener: HTMLElement;
  readonly form: EscalationForm;
  /** What the form still needs; empty before the first press of Escalate ticket. */
  readonly errors: EscalationErrors;
  readonly isPending: boolean;
  /** The last failed escalation of this dialog, in plain language. */
  readonly failure?: FailureView;
};

/** Escalate ticket and its dialog. */
export type Escalation = {
  /** True when `backend` allows the escalation (`escalate`). */
  readonly canEscalate: boolean;
  /** The dialog while it is open. */
  readonly dialog: EscalationDialogState | undefined;
  /** Opens the dialog with an empty form (Escalate ticket in the action bar). */
  readonly open: (opener: HTMLElement) => void;
  /** Changes the form. */
  readonly change: (update: (form: EscalationForm) => EscalationForm) => void;
  /** Checks the form and escalates (Escalate ticket in the dialog). */
  readonly submit: () => void;
  /** Closes the dialog without an escalation (Cancel). */
  readonly cancel: () => void;
};

/** The dialog as the hook keeps it. */
type OpenedDialog = {
  readonly opener: HTMLElement;
  readonly form: EscalationForm;
  /** True once staff pressed Escalate ticket in this dialog. */
  readonly isChecked: boolean;
};

/**
 * Keep Escalate ticket of a ticket.
 *
 * @param ticketId - The ticket of the address.
 * @param ticket - What the composer reads of the ticket: its allowed actions and suggestion.
 * @param onEscalated - Called once the ticket was escalated.
 * @returns Whether the escalation is allowed, the open dialog, and its handlers.
 */
export function useEscalation(
  ticketId: string,
  ticket: ComposerTicket,
  onEscalated: () => void,
): Escalation {
  const [opened, setOpened] = useState<OpenedDialog | undefined>(undefined);
  const createEscalation = useCreateEscalation(ticketId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  const canEscalate = ticket.allowedActions.has("escalate");
  return {
    canEscalate,
    dialog: opened === undefined ? undefined : toDialogState(opened, createEscalation),
    open: (opener) => {
      if (canEscalate) {
        createEscalation.reset();
        setOpened({ opener, form: emptyEscalationForm, isChecked: false });
      }
    },
    change: (update) => {
      setOpened((current) => current && { ...current, form: update(current.form) });
    },
    submit: () => {
      if (opened !== undefined && !createEscalation.isPending) {
        sendEscalation(
          opened,
          { mutation: createEscalation, createIdempotencyKey, suggestionId: ticket.suggestionId },
          { setDialog: setOpened, onEscalated },
        );
      }
    },
    cancel: () => {
      if (!createEscalation.isPending) {
        setOpened(undefined);
      }
    },
  };
}

/**
 * Show the open dialog.
 *
 * @param opened - The dialog as the hook keeps it.
 * @param mutation - The state of `createEscalation`.
 * @param mutation.isPending - True while the escalation is sent.
 * @param mutation.error - The error of the last escalation, or null.
 * @returns The form, its errors once checked, whether it is sent, and the last failure.
 */
function toDialogState(
  opened: OpenedDialog,
  mutation: { readonly isPending: boolean; readonly error: Error | null },
): EscalationDialogState {
  const failure = getRequestFailure(mutation.error);
  return {
    opener: opened.opener,
    form: opened.form,
    errors: opened.isChecked ? findEscalationErrors(opened.form) : {},
    isPending: mutation.isPending,
    ...(failure === undefined ? {} : { failure: describeReplyFailure(failure, "escalate") }),
  };
}

/** What sending an escalation needs. */
type EscalationSending = {
  readonly mutation: ReturnType<typeof useCreateEscalation>;
  readonly createIdempotencyKey: () => string;
  /** The current suggestion that staff saw; undefined without one. */
  readonly suggestionId: string | undefined;
};

/**
 * Check the form of the dialog and, when it has no error, send the escalation.
 *
 * @param opened - The open dialog.
 * @param sending - The mutation, the key factory, and the current suggestion.
 * @param callbacks - What changes the dialog, and what happens once the ticket was escalated.
 * @param callbacks.setDialog - Shows the dialog with its errors, or closes it after the escalation.
 * @param callbacks.onEscalated - Called once the ticket was escalated and the dialog closed.
 */
function sendEscalation(
  opened: OpenedDialog,
  sending: EscalationSending,
  callbacks: {
    readonly setDialog: (dialog: OpenedDialog | undefined) => void;
    readonly onEscalated: () => void;
  },
): void {
  if (Object.keys(findEscalationErrors(opened.form)).length > 0) {
    callbacks.setDialog({ ...opened, isChecked: true });
    return;
  }
  const request = buildEscalationRequest(opened.form, sending.suggestionId);
  const idempotencyKey = chooseEscalationKey(
    request,
    sending.mutation,
    sending.createIdempotencyKey,
  );
  sending.mutation.mutate(
    { request, idempotencyKey },
    {
      onSuccess: () => {
        callbacks.setDialog(undefined);
        callbacks.onEscalated();
      },
    },
  );
}

/**
 * Choose the `Idempotency-Key` of an escalation: the key of the failed one when staff send the
 * same escalation again, so it happens once (TS-29); a new key otherwise.
 *
 * @param request - The escalation to send.
 * @param mutation - The state of `createEscalation`, with the last request when it failed.
 * @param createIdempotencyKey - Creates a new key.
 * @returns The key.
 */
function chooseEscalationKey(
  request: CreateEscalationRequestContract,
  mutation: { readonly isError: boolean; readonly variables: RequestedEscalation | undefined },
  createIdempotencyKey: () => string,
): string {
  const failed = mutation.isError ? mutation.variables : undefined;
  return failed !== undefined && JSON.stringify(failed.request) === JSON.stringify(request)
    ? failed.idempotencyKey
    : createIdempotencyKey();
}
