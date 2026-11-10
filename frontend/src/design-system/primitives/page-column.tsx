/**
 * The content column of an area: at most 960 px wide in the shop and 1040 px in the admin area,
 * with the padding of the designs (shop UI design and admin UI design, Layout).
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const pageColumnVariants = cva("mx-auto flex w-full flex-col", {
  variants: {
    area: {
      shop: "max-w-shop gap-4 px-4 py-4 sm:gap-6 sm:px-6 sm:py-8",
      admin: "max-w-admin gap-4 p-6",
    },
  },
});

/** The area whose column width applies. */
export type PageColumnArea = "shop" | "admin";

/** Props of {@link PageColumn}. */
export type PageColumnProps = {
  readonly area: PageColumnArea;
  readonly children: ReactNode;
};

/**
 * Render the main content column. It is the `main` landmark of the page.
 *
 * @param props - The area and the content.
 * @returns The `main` element.
 */
export function PageColumn({ area, children }: PageColumnProps) {
  return <main className={pageColumnVariants({ area })}>{children}</main>;
}
