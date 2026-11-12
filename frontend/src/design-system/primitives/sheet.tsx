/**
 * A panel over the right side of the screen, on Radix Dialog (UI-31; console UI design, KB
 * document version): content that staff read without leaving the ticket. Radix moves the focus
 * into it, keeps it there, and closes it on Escape, a click outside, or Close. The sheet is open
 * while it is mounted, and the caller says where the focus goes when it closes (UI-30).
 */
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { type LucideIcon, X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/design-system/primitives/class-names";
import {
  type DialogReturnFocus,
  returnFocusAfterDialog,
} from "@/design-system/primitives/dialog-return-focus";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";
import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link Sheet}. */
export type SheetProps = {
  readonly icon: LucideIcon;
  /** The title, which is also the accessible name of the sheet. */
  readonly title: string;
  readonly returnFocus: DialogReturnFocus;
  readonly onClose: () => void;
  readonly children: ReactNode;
};

/**
 * Render the open sheet.
 *
 * @param props - The icon, the title, the focus target, the close handler, and the content.
 * @returns The sheet, in a portal.
 */
export function Sheet({ icon, title, returnFocus, onClose, children }: SheetProps) {
  return (
    <DialogPrimitive.Root
      open
      onOpenChange={(isNowOpen) => {
        if (!isNowOpen) {
          onClose();
        }
      }}
    >
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-20 bg-text/40" />
        <DialogPrimitive.Content
          aria-describedby={undefined}
          className="fixed inset-y-0 right-0 z-20 flex w-full max-w-sheet flex-col bg-surface-raised shadow-lg"
          onCloseAutoFocus={(event) => {
            returnFocusAfterDialog(event, returnFocus);
          }}
        >
          <div className="flex items-center gap-2 border-b border-border px-6 py-4">
            <Icon icon={icon} />
            <DialogPrimitive.Title className="min-w-0 flex-1 text-base font-semibold wrap-break-word text-text">
              {title}
            </DialogPrimitive.Title>
            <DialogPrimitive.Close
              aria-label="Close"
              className={cn("rounded-sm p-1 text-text-muted hover:text-text", FOCUS_RING_CLASSES)}
            >
              <Icon icon={X} />
            </DialogPrimitive.Close>
          </div>
          <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-6 py-4">
            {children}
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
