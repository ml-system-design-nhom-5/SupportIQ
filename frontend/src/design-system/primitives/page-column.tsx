/**
 * The content column of an area: at most 960 px wide in the shop and 1040 px in the admin area,
 * with the padding of the designs (shop UI design and admin UI design, Layout). A console screen
 * without the inbox, such as Reports (console UI design, Screens and reports.png), fills the space
 * below the app bar instead, with the 24 px padding and the 16 px gap of the mockup. The console
 * shell has the height of the window, so that column scrolls on its own and the app bar stays
 * visible.
 */
import { cva } from "class-variance-authority";
import type { ReactNode } from "react";

const pageColumnVariants = cva("flex flex-col", {
  variants: {
    area: {
      shop: "mx-auto w-full max-w-shop gap-4 px-4 py-4 sm:gap-6 sm:px-6 sm:py-8",
      admin: "mx-auto w-full max-w-admin gap-4 p-6",
      console: "min-h-0 min-w-0 flex-1 gap-4 overflow-y-auto p-6",
    },
  },
});

/**
 * The area whose column applies. `console` is a console screen without the inbox, inside the
 * console shell.
 */
export type PageColumnArea = "shop" | "admin" | "console";

/** Props of {@link PageColumn}. */
export type PageColumnProps = {
  readonly area: PageColumnArea;
  readonly children: ReactNode;
};

/**
 * Render the main content column. It is the `main` landmark of the page.
 *
 * @param props - The area and the content.
 * @returns The `main` element, which scrolls on its own in the console.
 */
export function PageColumn({ area, children }: PageColumnProps) {
  return <main className={pageColumnVariants({ area })}>{children}</main>;
}
