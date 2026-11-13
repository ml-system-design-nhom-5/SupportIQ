/**
 * The plain-text reply editor (console UI design, Draft editing and citations; state-editing.png
 * and state-placeholder.png). Marked parts, such as text in the placeholder syntax, stay
 * highlighted while staff type (UI-43): a backdrop behind the transparent text area holds the same
 * text with the same font, border, padding, line height, and wrapping, and draws a `mark` behind
 * each marked part. Both share one grid cell, so the editor grows with its text and neither layer
 * scrolls; a scroll that the browser still makes to keep the caret in view is copied to the
 * backdrop. The caller passes the marked parts: the editor never decides what a placeholder is.
 * Hint lines under the editor, such as "Edited text is not checked against the sources.",
 * describe it (`aria-describedby`). Text is plain text (SEC-22).
 */
import { Info } from "lucide-react";
import { useId, useRef } from "react";

import { InlineMessage } from "@/design-system/components/inline-message";
import { MarkedText, type MarkedTextPart } from "@/design-system/components/marked-text";
import { cn } from "@/design-system/primitives/class-names";
import { FOCUS_RING_CLASSES } from "@/design-system/primitives/focus-ring";

/** The rows of an empty editor (state-rejected.png). */
const MIN_ROW_COUNT = 4;

/**
 * Ends the backdrop text, so a final line break gets its line, as it does in the text area. A
 * space at the end of a line never wraps it.
 */
const BACKDROP_END = " ";

/** The classes that the text area and its backdrop share, so their text lines up (CODE-48). */
const LAYER_CLASSES =
  "col-start-1 row-start-1 w-full overflow-hidden rounded-md border p-3 text-sm wrap-break-word whitespace-pre-wrap";

/** Props of {@link ReplyEditor}. */
export type ReplyEditorProps = {
  /** The accessible name of the editor; the heading of the reply area shows what it is. */
  readonly label: string;
  readonly value: string;
  readonly onChange: (value: string) => void;
  /** The runs of `value` in order, each marked or not; joined, they give `value`. */
  readonly markedParts: readonly MarkedTextPart[];
  /** Shown while the editor is empty, such as "Write the reply to the customer". */
  readonly placeholder?: string;
  /** Lines under the editor, each with an Info icon; they describe the editor. */
  readonly hints?: readonly string[];
  /** The most characters the editor takes. */
  readonly maxLength?: number;
};

/**
 * Render the editor and its hints.
 *
 * @param props - The name, the text and its handler, the marked runs, the placeholder, the hints,
 *   and the length limit.
 * @returns The editor.
 */
export function ReplyEditor({
  label,
  value,
  onChange,
  markedParts,
  placeholder,
  hints = [],
  maxLength,
}: ReplyEditorProps) {
  const hintsId = useId();
  const backdropRef = useRef<HTMLDivElement>(null);
  const hasHints = hints.length > 0;
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-1 rounded-md bg-surface">
        <div
          ref={backdropRef}
          aria-hidden="true"
          className={cn(LAYER_CLASSES, "border-transparent text-transparent")}
        >
          <MarkedText parts={markedParts} layer="backdrop" />
          {BACKDROP_END}
        </div>
        <textarea
          aria-label={label}
          aria-describedby={hasHints ? hintsId : undefined}
          value={value}
          rows={MIN_ROW_COUNT}
          placeholder={placeholder}
          maxLength={maxLength}
          className={cn(
            LAYER_CLASSES,
            "resize-none border-border-strong bg-transparent text-text placeholder:text-text-muted",
            FOCUS_RING_CLASSES,
          )}
          onChange={(event) => {
            onChange(event.target.value);
          }}
          onScroll={(event) => {
            const backdrop = backdropRef.current;
            if (backdrop !== null) {
              backdrop.scrollTop = event.currentTarget.scrollTop;
            }
          }}
        />
      </div>
      {hasHints ? (
        <div id={hintsId} className="flex flex-col gap-1">
          {hints.map((hint) => (
            <InlineMessage key={hint} tone="muted" icon={Info}>
              {hint}
            </InlineMessage>
          ))}
        </div>
      ) : null}
    </div>
  );
}
