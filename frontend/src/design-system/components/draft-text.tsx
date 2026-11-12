/**
 * The text of an AI draft (console UI design, Draft editing and citations): paragraphs of
 * segments, each followed by its citation markers. Text is rendered as text, never as HTML
 * (SEC-22), and exactly as `backend` returns it (UI-43).
 */
import { Fragment, type ReactNode } from "react";

/** One segment and the markers after it. */
export type DraftTextSegment = {
  readonly segmentId: string;
  readonly text: string;
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
};

/**
 * Render the draft.
 *
 * @param props - The paragraphs.
 * @returns The paragraphs, with one space between the segments of a paragraph.
 */
export function DraftText({ paragraphs }: DraftTextProps) {
  return (
    <div className="flex flex-col gap-3 text-sm text-text">
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
