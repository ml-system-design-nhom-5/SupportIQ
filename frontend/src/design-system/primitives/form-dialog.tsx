/**
 * A modal dialog with a form, on Radix Dialog (UI-31; account management design, Create account
 * dialog). Radix AlertDialog stays for confirmations that ask for no input ({@link ConfirmDialog}).
 * Radix moves the focus into the dialog, keeps it there, and closes it on Escape or a click outside;
 * neither closes it, nor does Cancel, while the form is sent. The dialog is open while it is
 * mounted, and the caller says where the focus goes when it closes (UI-30).
 */
import * as DialogPrimitive from "@radix-ui/react-dialog";
import type { LucideIcon } from "lucide-react";
import type { ReactNode, SubmitEvent } from "react";

import { Button } from "@/design-system/primitives/button";
import type {
  ConfirmDialogText,
  ConfirmDialogTone,
} from "@/design-system/primitives/confirm-dialog";
import {
  type DialogReturnFocus,
  returnFocusAfterDialog,
} from "@/design-system/primitives/dialog-return-focus";
import { Text } from "@/design-system/primitives/text";

/**
 * The texts of a {@link FormDialog}. The tone of the description is that of
 * {@link ConfirmDialogText}: `muted` in the console dialogs, `default` in the admin dialogs.
 */
export type FormDialogText = Pick<ConfirmDialogText, "descriptionTone"> & {
  readonly title: string;
  /** Text under the title, such as what the change does; absent when the fields say enough. */
  readonly description?: ReactNode;
  /** A verb that names the result (UI-27). */
  readonly submitLabel: string;
  /** The icon before the submit label, such as the arrow of Escalate ticket. */
  readonly submitIcon?: LucideIcon;
};

/** Props of {@link FormDialog}. */
export type FormDialogProps = {
  readonly text: FormDialogText;
  readonly returnFocus: DialogReturnFocus;
  /** `danger` makes the submit button a `danger` button, for a change that is hard to undo. */
  readonly tone?: ConfirmDialogTone;
  /** True while the form is sent: no button acts and the dialog stays open, so it is sent once. */
  readonly isPending: boolean;
  readonly onSubmit: () => void;
  readonly onCancel: () => void;
  /** The fields of the form, and a banner after a failed submission. */
  readonly children: ReactNode;
};

/**
 * Render the dialog with its form, Cancel, and the submit button.
 *
 * @param props - The texts, the focus target, the tone, the pending state, the handlers, and the
 *   fields.
 * @returns The open dialog.
 */
export function FormDialog({
  text,
  returnFocus,
  tone = "default",
  isPending,
  onSubmit,
  onCancel,
  children,
}: FormDialogProps) {
  const handleSubmit = (event: SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!isPending) {
      onSubmit();
    }
  };

  return (
    <DialogPrimitive.Root
      open
      onOpenChange={(isNowOpen) => {
        if (!isNowOpen && !isPending) {
          onCancel();
        }
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-20 bg-text/40" />
        <DialogPrimitive.Content
          className="fixed top-1/2 left-1/2 z-20 flex max-h-screen w-full max-w-form-dialog -translate-1/2 flex-col gap-4 overflow-y-auto rounded-lg bg-surface-raised p-6 shadow-lg"
          {...(text.description === undefined ? { "aria-describedby": undefined } : {})}
          onCloseAutoFocus={(event) => {
            returnFocusAfterDialog(event, returnFocus);
          }}
        >
          <DialogPrimitive.Title className="text-lg font-semibold text-text">
            {text.title}
          </DialogPrimitive.Title>
          {text.description === undefined ? null : (
            <DialogPrimitive.Description className="text-sm">
              <Text tone={text.descriptionTone ?? "default"}>{text.description}</Text>
            </DialogPrimitive.Description>
          )}
          <form noValidate className="flex flex-col gap-4" onSubmit={handleSubmit}>
            {children}
            <div className="flex justify-end gap-2">
              <DialogPrimitive.Close asChild>
                <Button variant="secondary" disabled={isPending}>
                  Cancel
                </Button>
              </DialogPrimitive.Close>
              <Button
                type="submit"
                variant={tone === "danger" ? "danger" : "primary"}
                {...(text.submitIcon === undefined ? {} : { leadingIcon: text.submitIcon })}
                isPending={isPending}
              >
                {text.submitLabel}
              </Button>
            </div>
          </form>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
