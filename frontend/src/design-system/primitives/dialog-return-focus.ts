/**
 * Where the focus goes when a dialog closes (UI-30). The dialogs open from a button of a screen and
 * have no Radix Trigger, so Radix cannot return the focus; the caller says where it goes.
 */

/** Where the focus goes when a dialog closes. */
export type DialogReturnFocus = {
  /** The element that opened the dialog. */
  readonly opener: HTMLElement;
  /** The ID of a stable element, for when the outcome of the dialog replaced or disabled the opener. */
  readonly fallbackId: string;
};

/**
 * Move the focus to the opener of a dialog, or to its fallback when the opener is gone or disabled,
 * because a disabled button cannot take the focus. Radix calls it as the `onCloseAutoFocus` handler
 * of the dialog content, also when the dialog unmounts while open, a moment after it closed. When
 * the outcome of the dialog already moved the focus in that moment, such as to the reply that was
 * sent, the focus stays there.
 *
 * @param event - The close event of Radix, whose default focus move is cancelled.
 * @param returnFocus - The opener and the fallback.
 */
export function returnFocusAfterDialog(event: Event, returnFocus: DialogReturnFocus): void {
  event.preventDefault();
  if (document.activeElement !== null && document.activeElement !== document.body) {
    return;
  }
  const { opener, fallbackId } = returnFocus;
  const target =
    opener.isConnected && !opener.matches(":disabled")
      ? opener
      : document.getElementById(fallbackId);
  target?.focus();
}
