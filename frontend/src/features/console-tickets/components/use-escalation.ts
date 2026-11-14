/**
 * Escalate ticket of the reply area (console UI design, Actions and Dialogs; ADR-0006): the button
 * opens a dialog with the staff reason codes and a note, and the dialog's Escalate ticket sends
 * `createEscalation`. The AI only recommends an escalation; only this staff action decides it.
 * Like the dialogs of the admin area, the form is checked when staff press Escalate ticket, and
 * its errors stay until the next press. The request is built at that press, with the current
 * suggestion, because staff may escalate while a suggestion part is `pending`. The dialog closes
 * without an escalation when the suggestion that staff saw is replaced or `backend` no longer
 * allows the escalation, so a decision is never recorded for a suggestion staff did not see.
 */
import { useState } from "react";

import { useCreateIdempotencyKey } from "@/features/backend-requests";
import type { CreateEscalationRequestContract } from "@/features/console-tickets/api/contract-types";
import { chooseIdempotencyKey, type LastWrite } from "@/features/console-tickets/api/keyed-writes";
import { useCreateEscalation } from "@/features/console-tickets/api/use-create-escalation";
import type { ComposerTicket } from "@/features/console-tickets/model/composer-ticket";
import {
  buildEscalationRequest,
  emptyEscalationForm,
  type EscalationErrors,
  type EscalationForm,
  findEscalationErrors,
} from "@/features/console-tickets/model/escalation-form";
import type { FailureView } from "@/features/console-tickets/model/failure-view";
import {
  type DatedFailure,
  readDatedFailure,
} from "@/features/console-tickets/model/reply-failure";

/** The open dialog. */
export type EscalationDialogState = {
  /** The Escalate ticket button that opened it. */
  readonly opener: HTMLElement;
  readonly form: EscalationForm;
  /** What the form needed at the last press of Escalate ticket; empty before it. */
  readonly errors: EscalationErrors;
  readonly isPending: boolean;
  /** The last failed escalation, in plain language. */
  readonly failure?: FailureView;
};

/** Escalate ticket and its dialog. */
export type Escalation = {
  /** True when `backend` allows the escalation (`escalate`). */
  readonly canEscalate: boolean;
  /** True while the escalation is sending, with its automatic retries. */
  readonly isEscalating: boolean;
  /** The dialog while it is open. */
  readonly dialog: EscalationDialogState | undefined;
  /** The last failed escalation while the dialog is closed; the reply area shows it then. */
  readonly closedFailure: DatedFailure | undefined;
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
  readonly errors: EscalationErrors;
  /** The suggestion that staff saw when they opened the dialog. */
  readonly suggestionId: string | undefined;
};

/** The state of `createEscalation` that the hook reads. */
type EscalationMutation = ReturnType<typeof useCreateEscalation>;

/**
 * Keep Escalate ticket of a ticket.
 *
 * @param ticketId - The ticket of the address.
 * @param ticket - What the composer reads of the ticket: its allowed actions and suggestion.
 * @param onEscalated - Called once the ticket was escalated.
 * @returns Whether the escalation is allowed and sending, the open dialog, and its handlers.
 */
export function useEscalation(
  ticketId: string,
  ticket: ComposerTicket,
  onEscalated: () => void,
): Escalation {
  const [stored, setOpened] = useState<OpenedDialog | undefined>(undefined);
  const createEscalation = useCreateEscalation(ticketId);
  const createIdempotencyKey = useCreateIdempotencyKey();
  const canEscalate = ticket.allowedActions.has("escalate");
  const isStale = stored !== undefined && isOutdated(stored, ticket, createEscalation.isPending);
  if (isStale) {
    setOpened(undefined);
  }
  const opened = isStale ? undefined : stored;
  return {
    canEscalate,
    isEscalating: createEscalation.isPending,
    ...describeDialog(opened, createEscalation),
    open: (opener) => {
      if (canEscalate && !createEscalation.isPending) {
        const { suggestionId } = ticket;
        setOpened({ opener, form: emptyEscalationForm, errors: {}, suggestionId });
      }
    },
    change: (update) => {
      setOpened((current) => current && { ...current, form: update(current.form) });
    },
    submit: () => {
      if (opened !== undefined && !createEscalation.isPending) {
        const sending = { mutation: createEscalation, createIdempotencyKey };
        sendEscalation(opened, sending, { setDialog: setOpened, onEscalated });
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
 * Check the form of the dialog and, when it has no error, send the escalation with the
 * suggestion that staff saw.
 *
 * @param opened - The open dialog.
 * @param sending - The mutation and the factory of new keys.
 * @param sending.mutation - The mutation of `createEscalation`.
 * @param sending.createIdempotencyKey - Creates a new key.
 * @param callbacks - What changes the dialog, and what happens once the ticket was escalated.
 * @param callbacks.setDialog - Shows the dialog with its errors, or closes it after the escalation.
 * @param callbacks.onEscalated - Called once the ticket was escalated and the dialog closed.
 */
function sendEscalation(
  opened: OpenedDialog,
  sending: {
    readonly mutation: EscalationMutation;
    readonly createIdempotencyKey: () => string;
  },
  callbacks: {
    readonly setDialog: (dialog: OpenedDialog | undefined) => void;
    readonly onEscalated: () => void;
  },
): void {
  const errors = findEscalationErrors(opened.form);
  callbacks.setDialog({ ...opened, errors });
  if (Object.keys(errors).length > 0) {
    return;
  }
  const request = buildEscalationRequest(opened.form, opened.suggestionId);
  const lastWrite: LastWrite<CreateEscalationRequestContract> = sending.mutation;
  const idempotencyKey = chooseIdempotencyKey(request, lastWrite, sending.createIdempotencyKey);
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
 * Tell whether the open dialog no longer matches the ticket: a new suggestion replaced the one
 * that staff saw, or `backend` no longer allows the escalation. A dialog that is sending stays.
 *
 * @param opened - The open dialog.
 * @param ticket - The ticket as rendered now.
 * @param isPending - True while the escalation is sending.
 * @returns True when the dialog must close without an escalation.
 */
function isOutdated(opened: OpenedDialog, ticket: ComposerTicket, isPending: boolean): boolean {
  return (
    !isPending &&
    (opened.suggestionId !== ticket.suggestionId || !ticket.allowedActions.has("escalate"))
  );
}

/**
 * Show the dialog while it is open, or the last failure in the reply area while it is closed.
 *
 * @param opened - The open dialog; undefined while it is closed.
 * @param mutation - The state of `createEscalation`.
 * @returns The dialog with its form, errors, sending state, and last failure; or the failure.
 */
function describeDialog(
  opened: OpenedDialog | undefined,
  mutation: EscalationMutation,
): Pick<Escalation, "dialog" | "closedFailure"> {
  const failure = readDatedFailure(mutation, "escalate");
  if (opened === undefined) {
    return { dialog: undefined, closedFailure: failure };
  }
  const dialog: EscalationDialogState = {
    opener: opened.opener,
    form: opened.form,
    errors: opened.errors,
    isPending: mutation.isPending,
    ...(failure === undefined ? {} : { failure: failure.view }),
  };
  return { dialog, closedFailure: undefined };
}
