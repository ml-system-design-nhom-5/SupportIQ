/**
 * A heading in the type scale of UI-08. The level keeps the page outline; the size follows the
 * role of the heading on the screen.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const headingVariants = cva("font-semibold text-text", {
  variants: {
    size: { page: "text-xl sm:text-2xl", section: "text-lg", item: "text-base" },
  },
});

const elementByLevel = { 1: "h1", 2: "h2", 3: "h3" } as const;

/** `page` is the title of a screen; `section` a block; `item` the name of an item. */
export type HeadingSize = "page" | "section" | "item";

/** Props of {@link Heading}. */
export type HeadingProps = {
  readonly level: 1 | 2 | 3;
  readonly size?: HeadingSize;
  readonly children: ReactNode;
};

/**
 * Render a heading.
 *
 * @param props - The level, the size, and the text.
 * @returns The heading element.
 */
export function Heading({ level, size = "page", children }: HeadingProps) {
  const Element = elementByLevel[level];
  return <Element className={headingVariants({ size })}>{children}</Element>;
}
