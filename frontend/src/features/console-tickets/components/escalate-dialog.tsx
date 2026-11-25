/**
 * The Escalate ticket dialog (console UI design, Dialogs, dialog-escalate.png): staff move the
 * ticket to a manager with at least one staff reason code, and a note when the code is Other
 * (ADR-0006). It only shows the form: the caller checks it, sends the escalation, and closes the
 * dialog.
 */
import { CircleArrowUp } from "lucide-react";
import { useId } from "react";

import {
  type DialogReturnFocus,
  FormDialog,
  FormField,
  getFieldDescriptionId,
  TextInput,
  ToggleChipGroup,
} from "@/design-system";
import { FailureViewBanner } from "@/features/console-tickets/components/failure-view-banner";
import type { EscalationErrors } from "@/features/console-tickets/model/escalation-form";
import type { FailureView } from "@/features/console-tickets/model/failure-view";
import {
  type StaffReasonCode,
  staffReasonOptions,
} from "@/features/console-tickets/model/staff-reason-codes";

/** The fields of the dialog and their handlers. */
export type EscalateDialogForm = {
  readonly reasonCodes: ReadonlySet<StaffReasonCode>;
  readonly note: string;
  /** The errors of the last check; absent before a check and after one that passed. */
  readonly errors?: EscalationErrors;
  readonly onToggle: (reasonCode: StaffReasonCode) => void;
  readonly onNoteChange: (note: string) => void;
};

/** The state of the escalation request and the handlers of the two buttons. */
export type EscalateDialogSubmission = {
  /** True while the escalation is sent: no button acts and the dialog stays open. */
  readonly isPending: boolean;
  /** Why the last escalation failed, shown in the dialog. */
  readonly failure?: FailureView;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
};

/** Props of {@link EscalateDialog}. */
export type EscalateDialogProps = {
  readonly ticketId: string;
  readonly returnFocus: DialogReturnFocus;
  readonly form: EscalateDialogForm;
  readonly submission: EscalateDialogSubmission;
};

/**
 * Render the dialog.
 *
 * @param props - The ticket ID, the focus target, the form, and the state of the request.
 * @returns The open dialog.
 */
export function EscalateDialog({ ticketId, returnFocus, form, submission }: EscalateDialogProps) {
  const noteId = useId();
  const reasonsError = form.errors?.reasons;
  const noteError = form.errors?.note;
  return (
    <FormDialog
      text={{
        title: `Escalate ticket ${ticketId} to a manager?`,
        description: "Choose at least one reason. The ticket becomes read-only for you.",
        descriptionTone: "muted",
        submitLabel: "Escalate ticket",
        submitIcon: CircleArrowUp,
      }}
      returnFocus={returnFocus}
      isPending={submission.isPending}
      onSubmit={submission.onSubmit}
      onCancel={submission.onCancel}
    >
      <ToggleChipGroup
        label="Why do you escalate this ticket?"
        labelVisibility="hidden"
        options={staffReasonOptions}
        selected={form.reasonCodes}
        onToggle={form.onToggle}
        {...(reasonsError === undefined ? {} : { error: reasonsError })}
      />
      <FormField inputId={noteId} label="Note (required with Other)" error={noteError}>
        <TextInput
          id={noteId}
          value={form.note}
          aria-invalid={noteError !== undefined}
          aria-describedby={getFieldDescriptionId({ inputId: noteId, error: noteError })}
          onChange={(event) => {
            form.onNoteChange(event.target.value);
          }}
        />
      </FormField>
      {submission.failure === undefined ? null : <FailureViewBanner failure={submission.failure} />}
    </FormDialog>
  );
}
