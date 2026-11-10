/**
 * One message of a support thread: the customer's message on the right, the reply from support on
 * the left with a `success` edge (shop UI design, Support for this order). The text is rendered as
 * text and keeps its line breaks (SEC-22).
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const rowVariants = cva("flex", {
  variants: { author: { customer: "justify-end", support: "justify-start" } },
});

const bubbleVariants = cva("flex max-w-9/10 flex-col gap-1 rounded-lg px-4 py-3 sm:max-w-4/5", {
  variants: {
    author: {
      customer: "bg-background",
      support: "border border-l-4 border-border border-l-success bg-surface",
    },
  },
});

/** Who wrote the message. */
export type MessageAuthor = "customer" | "support";

/** Props of {@link MessageBubble}. */
export type MessageBubbleProps = {
  readonly author: MessageAuthor;
  /** The author label and the time, for example "You · 3 weeks ago". */
  readonly header: ReactNode;
  /** The message text, exactly as written. */
  readonly text: string;
};

/**
 * Render a message.
 *
 * @param props - The author, the header line, and the text.
 * @returns The message row.
 */
export function MessageBubble({ author, header, text }: MessageBubbleProps) {
  return (
    <div className={rowVariants({ author })}>
      <div className={bubbleVariants({ author })}>
        <div className="flex flex-wrap items-center gap-1 text-sm text-text-muted">{header}</div>
        <p className="wrap-break-word whitespace-pre-wrap text-text">{text}</p>
      </div>
    </div>
  );
}
