/**
 * A console screen without the inbox, such as Reports (console UI design, Screens and
 * reports.png): the `main` landmark below the app bar, with the 24 px padding and the 16 px gap of
 * the mockup. The console shell has the height of the window, so the screen scrolls on its own and
 * the app bar stays visible.
 */
import type { ReactNode } from "react";

/** Props of {@link ConsolePage}. */
export type ConsolePageProps = {
  /** The screen: its header, then its content. */
  readonly children: ReactNode;
};

/**
 * Render a console screen that fills the space below the app bar.
 *
 * @param props - The screen.
 * @returns The `main` element, which scrolls on its own.
 */
export function ConsolePage({ children }: ConsolePageProps) {
  return (
    <main className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-y-auto p-6">
      {children}
    </main>
  );
}
