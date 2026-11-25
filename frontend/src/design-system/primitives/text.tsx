/**
 * Text in the type scale of UI-08. An ID in the text uses {@link Identifier}.
 * Customer and staff text is always rendered as text, never as HTML (SEC-22).
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const textVariants = cva("", {
  variants: {
    size: { xs: "text-xs", sm: "text-sm", base: "text-base", lg: "text-lg", xl: "text-xl" },
    tone: {
      default: "text-text",
      muted: "text-text-muted",
      success: "text-success",
      warning: "text-warning",
      danger: "text-danger",
      info: "text-info",
      inherit: "",
    },
    overflow: {
      wrap: "wrap-break-word",
      truncate: "truncate",
      preserve: "wrap-break-word whitespace-pre-wrap",
    },
  },
});

/** A size of the type scale: 12, 14, 16, 18, or 20 px. */
export type TextSize = "xs" | "sm" | "base" | "lg" | "xl";

/** A text color role of UI-06. `inherit` keeps the color of the parent. */
export type TextTone = "default" | "muted" | "success" | "warning" | "danger" | "info" | "inherit";

/**
 * How long text behaves: `wrap` breaks long words, `truncate` shows one line with an ellipsis,
 * and `preserve` also keeps the line breaks of a message.
 */
export type TextOverflow = "wrap" | "truncate" | "preserve";

/** Props of {@link Text}. */
export type TextProps = {
  readonly size?: TextSize;
  readonly tone?: TextTone;
  readonly overflow?: TextOverflow;
  readonly children: ReactNode;
};

/**
 * Render text.
 *
 * @param props - The size, the tone, the overflow, and the text.
 * @returns The text element.
 */
export function Text({ size = "sm", tone = "default", overflow = "wrap", children }: TextProps) {
  return <span className={textVariants({ size, tone, overflow })}>{children}</span>;
}
