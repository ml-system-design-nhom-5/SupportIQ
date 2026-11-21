/**
 * The header of a screen: its title, a line of meta information, and one action on the right.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const rowVariants = cva("flex flex-wrap", {
  variants: {
    density: { comfortable: "items-end gap-x-4 gap-y-3", compact: "items-center gap-3" },
  },
});

const titleVariants = cva("min-w-0 font-semibold text-text", {
  variants: { density: { comfortable: "text-xl sm:text-2xl", compact: "text-xl" } },
});

/** `comfortable` is the shop header; `compact` is the header of the admin area. */
export type PageHeaderDensity = "comfortable" | "compact";

/** Props of {@link PageHeader}. */
export type PageHeaderProps = {
  /** The `h1` of the screen. */
  readonly title: ReactNode;
  /** Short muted text next to the title, such as the date of an order. */
  readonly meta?: ReactNode;
  /** An action at the end of the row; it takes the full width at phone width. */
  readonly action?: ReactNode;
  readonly density?: PageHeaderDensity;
};

/**
 * Render the header of a screen.
 *
 * @param props - The title, the meta information, the action, and the density.
 * @returns The header row.
 */
export function PageHeader({ title, meta, action, density = "comfortable" }: PageHeaderProps) {
  return (
    <div className={rowVariants({ density })}>
      <h1 className={titleVariants({ density })}>{title}</h1>
      {meta === undefined ? null : <p className="text-sm text-text-muted">{meta}</p>}
      {action === undefined ? null : <div className="w-full sm:ml-auto sm:w-auto">{action}</div>}
    </div>
  );
}
