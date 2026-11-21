/**
 * A single panel in the middle of the page, as the Sign in screen of the console UI design shows.
 * It is the `main` landmark of the page.
 */
import type { ReactNode } from "react";

/** Props of {@link CenteredPanel}. */
export type CenteredPanelProps = {
  readonly children: ReactNode;
};

/**
 * Render the centered panel.
 *
 * @param props - The content.
 * @returns The `main` element with the panel.
 */
export function CenteredPanel({ children }: CenteredPanelProps) {
  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <div className="flex w-full max-w-sign-in flex-col gap-3 rounded-lg border border-border bg-surface p-6 shadow-sm">
        {children}
      </div>
    </main>
  );
}
