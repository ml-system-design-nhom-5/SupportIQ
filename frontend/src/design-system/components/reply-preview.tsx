/**
 * The start of a reply in the Confirm Send reply dialog (UI-17; console UI design, Dialogs,
 * dialog-confirm-send.png): plain text with its line breaks (SEC-22) on a tinted box, clamped to
 * three lines with an ellipsis. Assistive technology still reads the whole text. It is made of
 * spans, so it can sit inside the description paragraph of a {@link ConfirmDialog}, where it
 * starts on its own line, one gap under the text before it.
 */

/** Props of {@link ReplyPreview}. */
export type ReplyPreviewProps = {
  /** The whole reply, exactly as it is sent. */
  readonly text: string;
};

/**
 * Render the start of the reply.
 *
 * @param props - The reply text.
 * @returns The quoted start of the reply.
 */
export function ReplyPreview({ text }: ReplyPreviewProps) {
  return (
    // The padding is on the outer box: on the clamped box, it would show part of the next line.
    <span className="mt-3 block rounded-md border border-border bg-background p-3">
      <span className="line-clamp-3 text-sm wrap-break-word whitespace-pre-wrap text-text">
        {text}
      </span>
    </span>
  );
}
