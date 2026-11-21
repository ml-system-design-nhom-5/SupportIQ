/**
 * The full text of a KB document version (UI-20; console UI design, kb-document.png), with the
 * passage that a citation or retrieval matched highlighted, so staff can check it against its
 * source. KB text is untrusted data and is rendered as plain text (SEC-22, SEC-24).
 */

const TEXT_CLASSES = "text-sm wrap-break-word whitespace-pre-wrap text-text";

/** Props of {@link KbDocumentText}. */
export type KbDocumentTextProps = {
  readonly body: string;
  /** The passage to highlight; absent, or not found in the body, highlights nothing. */
  readonly highlight?: string;
};

/**
 * Render the text.
 *
 * @param props - The full text and the passage to highlight.
 * @returns The text, with the first occurrence of the passage marked.
 */
export function KbDocumentText({ body, highlight }: KbDocumentTextProps) {
  const start = highlight === undefined || highlight === "" ? -1 : body.indexOf(highlight);
  if (highlight === undefined || start === -1) {
    return <p className={TEXT_CLASSES}>{body}</p>;
  }
  const end = start + highlight.length;
  return (
    <p className={TEXT_CLASSES}>
      {body.slice(0, start)}
      <mark className="rounded-sm bg-ai-subtle text-text">{body.slice(start, end)}</mark>
      {body.slice(end)}
    </p>
  );
}
