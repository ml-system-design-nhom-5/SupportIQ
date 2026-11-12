/**
 * The layout primitive of every screen (UI-02): a flex row or column with a gap from the spacing
 * tokens (UI-07). Features never style elements themselves.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const stackVariants = cva("flex min-w-0", {
  variants: {
    direction: { row: "flex-row", column: "flex-col" },
    gap: {
      "0": "gap-0",
      "1": "gap-1",
      "2": "gap-2",
      "3": "gap-3",
      "4": "gap-4",
      "6": "gap-6",
      "8": "gap-8",
      "12": "gap-12",
      "16": "gap-16",
    },
    align: {
      stretch: "items-stretch",
      start: "items-start",
      center: "items-center",
      end: "items-end",
      baseline: "items-baseline",
    },
    justify: {
      start: "justify-start",
      center: "justify-center",
      end: "justify-end",
      between: "justify-between",
    },
  },
});

/** A spacing step of UI-07: 0, 4, 8, 12, 16, 24, 32, 48, or 64 px. */
export type SpacingStep = "0" | "1" | "2" | "3" | "4" | "6" | "8" | "12" | "16";

/** The element that the stack renders, so lists and sections keep their semantics. */
export type StackElement =
  "div" | "section" | "article" | "header" | "footer" | "nav" | "ul" | "ol" | "li";

/** The main axis of the stack. */
export type StackDirection = "row" | "column";

/** Props of {@link Stack}. */
export type StackProps = {
  readonly as?: StackElement;
  readonly direction?: StackDirection;
  readonly gap?: SpacingStep;
  readonly align?: "stretch" | "start" | "center" | "end" | "baseline";
  readonly justify?: "start" | "center" | "end" | "between";
  /** Names a `section` or `nav` landmark when it has no visible heading. */
  readonly label?: string;
  readonly children: ReactNode;
};

/**
 * Lay out children in a row or a column.
 *
 * @param props - The element, the direction, the gap, the alignment, and the children.
 * @returns The stack.
 */
export function Stack({
  as: Element = "div",
  direction = "column",
  gap = "0",
  align = "stretch",
  justify = "start",
  label,
  children,
}: StackProps) {
  return (
    <Element aria-label={label} className={stackVariants({ direction, gap, align, justify })}>
      {children}
    </Element>
  );
}
