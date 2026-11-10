/**
 * A placeholder bar that stands in for content while it loads (UI-24). It does not move, so it
 * needs no motion token.
 */
import { cva } from "class-variance-authority";

const skeletonVariants = cva("block rounded-sm bg-border", {
  variants: {
    width: { full: "w-full", "three-quarters": "w-3/4", half: "w-1/2", third: "w-1/3" },
    height: { line: "h-3", block: "h-16" },
  },
});

/** The width of the bar, as a share of its container. */
export type SkeletonWidth = "full" | "three-quarters" | "half" | "third";

/** `line` is one line of text; `block` is a larger area, such as an image. */
export type SkeletonHeight = "line" | "block";

/** Props of {@link Skeleton}. */
export type SkeletonProps = {
  readonly width?: SkeletonWidth;
  readonly height?: SkeletonHeight;
};

/**
 * Render a placeholder bar, hidden from assistive technology. The region that contains it says
 * that it is loading.
 *
 * @param props - The width and the height.
 * @returns The bar.
 */
export function Skeleton({ width = "full", height = "line" }: SkeletonProps) {
  return <span aria-hidden="true" className={skeletonVariants({ width, height })} />;
}
