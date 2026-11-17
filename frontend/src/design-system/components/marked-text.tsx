/**
 * Text with marked parts, such as a placeholder in AI text (UI-43; console UI design, Draft
 * editing and citations, state-placeholder.png). Each marked part is a `mark` in the `warning`
 * role with an underline, so color is not the only signal (UI-11); the caller adds a hint line
 * that says what the mark means. Text is rendered as text, never as HTML (SEC-22). The caller
 * decides which parts are marked: this component never looks for placeholders itself.
 */
import { cva } from "class-variance-authority";
import { Fragment } from "react";

const markVariants = cva(
  "rounded-sm bg-warning-subtle underline decoration-warning underline-offset-2",
  { variants: { layer: { text: "text-warning", backdrop: "text-transparent" } } },
);

/**
 * `text` shows the text with its marks. `backdrop` draws only the marks, under transparent text,
 * behind an editor that shows the same text itself ({@link ReplyEditor}).
 */
export type MarkedTextLayer = "text" | "backdrop";

/** One run of the text, marked or not. */
export type MarkedTextPart = {
  /** The text of the run; never empty. */
  readonly text: string;
  readonly isMarked: boolean;
};

/** Props of {@link MarkedText}. */
export type MarkedTextProps = {
  /** The runs in order; joined, they give the whole text. */
  readonly parts: readonly MarkedTextPart[];
  readonly layer?: MarkedTextLayer;
};

/** A run with the offset where it starts in the whole text, which keys it. */
type PositionedPart = {
  readonly part: MarkedTextPart;
  readonly start: number;
};

/**
 * Render the text.
 *
 * @param props - The runs and the layer.
 * @returns The runs as inline content, each marked run in a `mark`.
 */
export function MarkedText({ parts, layer = "text" }: MarkedTextProps) {
  return (
    <>
      {toPositionedParts(parts).map(({ part, start }) =>
        part.isMarked ? (
          <mark key={start} className={markVariants({ layer })}>
            {part.text}
          </mark>
        ) : (
          <Fragment key={start}>{part.text}</Fragment>
        ),
      )}
    </>
  );
}

/**
 * Give each run the offset where it starts, a stable key even when two runs hold the same text.
 *
 * @param parts - The runs in order.
 * @returns The runs with their start offsets.
 */
function toPositionedParts(parts: readonly MarkedTextPart[]): readonly PositionedPart[] {
  const positioned: PositionedPart[] = [];
  let start = 0;
  for (const part of parts) {
    positioned.push({ part, start });
    start += part.text.length;
  }
  return positioned;
}
