/**
 * The confirmation of Send reply (UI-17; console UI design, Dialogs, dialog-confirm-send.png): it
 * names the customer, shows the start of the reply, and says that a sent reply cannot be changed.
 * Only its Send reply sends the reply (FR-04).
 */
import { ConfirmDialog, type DialogReturnFocus, ReplyPreview } from "@/design-system";

/** Props of {@link ConfirmSendDialog}. */
type ConfirmSendDialogProps = {
  readonly customerName: string;
  /** The text that the customer receives. */
  readonly body: string;
  readonly returnFocus: DialogReturnFocus;
  readonly isSending: boolean;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
};

/**
 * Render the confirmation.
 *
 * @param props - The customer, the reply, the focus target, the send state, and the handlers.
 * @returns The open dialog.
 */
export function ConfirmSendDialog({
  customerName,
  body,
  returnFocus,
  isSending,
  onConfirm,
  onCancel,
}: ConfirmSendDialogProps) {
  return (
    <ConfirmDialog
      isOpen
      text={{
        title: `Send this reply to ${customerName}?`,
        description: (
          <>
            The customer sees it in the shop right away. A sent reply cannot be changed.
            <ReplyPreview text={body} />
          </>
        ),
        confirmLabel: "Send reply",
        pendingLabel: "Sending…",
        cancelLabel: "Keep editing",
      }}
      returnFocus={returnFocus}
      isPending={isSending}
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
}
