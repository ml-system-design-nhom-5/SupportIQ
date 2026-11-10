/**
 * A confirmation dialog on Radix AlertDialog (UI-31). Radix moves focus into the dialog, keeps it
 * there, and closes on Escape. The dialog opens from a row of a list and has no Radix Trigger, so
 * Radix cannot return the focus; the caller says where it goes (UI-30).
 */
import * as AlertDialogPrimitive from "@radix-ui/react-alert-dialog";
import type { ReactNode } from "react";

import { Button } from "@/design-system/primitives/button";

/** `danger` marks a confirmation whose effect is hard to undo, such as Deactivate. */
export type ConfirmDialogTone = "default" | "danger";

/** The texts of a {@link ConfirmDialog}. */
export type ConfirmDialogText = {
  /** Names the account and the change (UI-45). */
  readonly title: string;
  readonly description: ReactNode;
  /** A verb that names the result (UI-27). */
  readonly confirmLabel: string;
  /** Shown on the confirm button while the change is sent. */
  readonly pendingLabel: string;
};

/** Where the focus goes when the dialog closes. */
export type ConfirmDialogReturnFocus = {
  /** The element that opened the dialog. */
  readonly opener: HTMLElement;
  /** The ID of a stable element, for when the confirmed change replaced the opener. */
  readonly fallbackId: string;
};

/** Props of {@link ConfirmDialog}. */
export type ConfirmDialogProps = {
  readonly isOpen: boolean;
  readonly text: ConfirmDialogText;
  readonly returnFocus: ConfirmDialogReturnFocus;
  readonly tone?: ConfirmDialogTone;
  /** True while the change is sent: neither button acts, so it is sent once. */
  readonly isPending: boolean;
  readonly onConfirm: () => void;
  readonly onCancel: () => void;
};

/**
 * Render a modal confirmation.
 *
 * @param props - The open state, the texts, the focus target, the tone, and the handlers.
 * @returns The dialog, or nothing while it is closed.
 */
export function ConfirmDialog({
  isOpen,
  text,
  returnFocus,
  tone = "default",
  isPending,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  return (
    <AlertDialogPrimitive.Root
      open={isOpen}
      onOpenChange={(isNowOpen) => {
        if (!isNowOpen && !isPending) {
          onCancel();
        }
      }}
    >
      <AlertDialogPrimitive.Portal>
        <AlertDialogPrimitive.Overlay className="fixed inset-0 z-20 bg-text/40" />
        <AlertDialogPrimitive.Content
          className="fixed top-1/2 left-1/2 z-20 flex w-full max-w-dialog -translate-1/2 flex-col gap-3 rounded-lg bg-surface-raised p-6 shadow-lg"
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            const { opener, fallbackId } = returnFocus;
            const target = opener.isConnected ? opener : document.getElementById(fallbackId);
            target?.focus();
          }}
        >
          <AlertDialogPrimitive.Title className="text-lg font-semibold text-text">
            {text.title}
          </AlertDialogPrimitive.Title>
          <AlertDialogPrimitive.Description className="text-sm text-text">
            {text.description}
          </AlertDialogPrimitive.Description>
          <div className="flex justify-end gap-2">
            <AlertDialogPrimitive.Cancel asChild>
              <Button variant="secondary" disabled={isPending}>
                Cancel
              </Button>
            </AlertDialogPrimitive.Cancel>
            <Button
              variant={tone === "danger" ? "danger" : "primary"}
              isPending={isPending}
              onClick={onConfirm}
            >
              {isPending ? text.pendingLabel : text.confirmLabel}
            </Button>
          </div>
        </AlertDialogPrimitive.Content>
      </AlertDialogPrimitive.Portal>
    </AlertDialogPrimitive.Root>
  );
}
