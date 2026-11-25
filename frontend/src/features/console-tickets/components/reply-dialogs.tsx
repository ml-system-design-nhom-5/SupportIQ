/**
 * The dialogs of the reply area while one is open (console UI design, Dialogs): the confirmation of
 * Send reply (UI-17) and Escalate ticket. When a dialog closes, the focus returns to the button
 * that opened it, or to the ticket heading when that button is gone or disabled (UI-30).
 */
import { ConfirmSendDialog } from "@/features/console-tickets/components/confirm-send-dialog";
import { EscalateDialog } from "@/features/console-tickets/components/escalate-dialog";
import type {
  Escalation,
  EscalationDialogState,
} from "@/features/console-tickets/components/use-escalation";
import type { ReplyComposer } from "@/features/console-tickets/components/use-reply-composer";
import { toggleStaffReasonCode } from "@/features/console-tickets/model/staff-reason-codes";

/** Props of {@link ReplyDialogs}. */
type ReplyDialogsProps = {
  readonly composer: ReplyComposer;
  readonly ticket: { readonly ticketId: string; readonly customerName: string };
  /** The ID of the ticket heading, where the focus goes when the opener is gone. */
  readonly fallbackId: string;
};

/**
 * Render the open dialog of the reply area.
 *
 * @param props - The composer, the ticket, and the fallback of the focus.
 * @returns The confirmation of Send reply, Escalate ticket, or nothing.
 */
export function ReplyDialogs({ composer, ticket, fallbackId }: ReplyDialogsProps) {
  const { confirmation, escalation } = composer;
  return (
    <>
      {confirmation === undefined ? null : (
        <ConfirmSendDialog
          customerName={ticket.customerName}
          body={confirmation.body}
          returnFocus={{ opener: confirmation.opener, fallbackId }}
          isSending={composer.isSending}
          onConfirm={composer.confirmSend}
          onCancel={composer.cancelSend}
        />
      )}
      {escalation.dialog === undefined ? null : (
        <OpenEscalateDialog
          escalation={escalation}
          dialog={escalation.dialog}
          ticketId={ticket.ticketId}
          fallbackId={fallbackId}
        />
      )}
    </>
  );
}

/**
 * Render Escalate ticket while it is open.
 *
 * @param props - The escalation, its open dialog, the ticket, and the fallback of the focus.
 * @returns The dialog.
 */
function OpenEscalateDialog({
  escalation,
  dialog,
  ticketId,
  fallbackId,
}: {
  readonly escalation: Escalation;
  readonly dialog: EscalationDialogState;
  readonly ticketId: string;
  readonly fallbackId: string;
}) {
  return (
    <EscalateDialog
      ticketId={ticketId}
      returnFocus={{ opener: dialog.opener, fallbackId }}
      form={{
        reasonCodes: dialog.form.reasonCodes,
        note: dialog.form.note,
        errors: dialog.errors,
        onToggle: (reasonCode) => {
          escalation.change((form) => ({
            ...form,
            reasonCodes: toggleStaffReasonCode(form.reasonCodes, reasonCode),
          }));
        },
        onNoteChange: (note) => {
          escalation.change((form) => ({ ...form, note }));
        },
      }}
      submission={{
        isPending: dialog.isPending,
        ...(dialog.failure === undefined ? {} : { failure: dialog.failure }),
        onSubmit: escalation.submit,
        onCancel: escalation.cancel,
      }}
    />
  );
}
