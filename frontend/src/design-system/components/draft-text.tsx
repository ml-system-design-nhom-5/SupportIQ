/**
 * The text of an AI draft (console UI design, Draft editing and citations): paragraphs of
 * segments, each followed by its citation markers. Text is rendered as text, never as HTML
 * (SEC-22), and exactly as `backend` returns it (UI-43); a segment can mark its placeholders with
 * {@link MarkedText}. A draft that staff rejected or that a new intent made outdated is `muted`
 * (state-rejected.png, state-intent-changed.png).
 */
import { cva } from "class-variance-authority";
import { Fragment, type ReactNode } from "react";

const draftTextVariants = cva("flex flex-col gap-3 text-sm", {
  variants: { tone: { default: "text-text", muted: "text-text-muted" } },
});

/** `muted` fades a rejected or outdated draft; `default` is the draft to review. */
export type DraftTextTone = "default" | "muted";

/** One segment and the markers after it. */
export type DraftTextSegment = {
  readonly segmentId: string;
  /** The text of the segment: plain text, or a {@link MarkedText} that marks its placeholders. */
  readonly text: ReactNode;
  /** The citation markers of the segment; absent when it cites nothing. */
  readonly markers?: ReactNode;
};

/** One paragraph of the draft. */
export type DraftTextParagraph = {
  readonly paragraphId: string;
  readonly segments: readonly DraftTextSegment[];
};

/** Props of {@link DraftText}. */
export type DraftTextProps = {
  readonly paragraphs: readonly DraftTextParagraph[];
  readonly tone?: DraftTextTone;
};

/**
 * Render the draft.
 *
 * @param props - The paragraphs and the tone.
 * @returns The paragraphs, with one space between the segments of a paragraph.
 */
export function DraftText({ paragraphs, tone = "default" }: DraftTextProps) {
  return (
    <div className={draftTextVariants({ tone })}>
      {paragraphs.map((paragraph) => (
        <p key={paragraph.paragraphId} className="wrap-break-word whitespace-pre-wrap">
          {paragraph.segments.map((segment, index) => (
            <Fragment key={segment.segmentId}>
              {index === 0 ? null : " "}
              {segment.text}
              {segment.markers}
            </Fragment>
          ))}
        </p>
      ))}
    </div>
  );
}
