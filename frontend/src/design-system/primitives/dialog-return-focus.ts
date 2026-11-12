/**
 * Where the focus goes when a dialog closes (UI-30). The dialogs open from a button of a screen and
 * have no Radix Trigger, so Radix cannot return the focus; the caller says where it goes.
 */

/** Where the focus goes when a dialog closes. */
export type DialogReturnFocus = {
  /** The element that opened the dialog. */
  readonly opener: HTMLElement;
  /** The ID of a stable element, for when the outcome of the dialog replaced the opener. */
  readonly fallbackId: string;
};

/**
 * Move the focus to the opener of a dialog, or to its fallback when the opener is gone. Radix calls
 * it as the `onCloseAutoFocus` handler of the dialog content.
 *
 * @param event - The close event of Radix, whose default focus move is cancelled.
 * @param returnFocus - The opener and the fallback.
 */
export function returnFocusAfterDialog(event: Event, returnFocus: DialogReturnFocus): void {
  event.preventDefault();
  const { opener, fallbackId } = returnFocus;
  const target = opener.isConnected ? opener : document.getElementById(fallbackId);
  target?.focus();
}
