/**
 * The frame of the console (console UI design, Layout): the app bar on top and the screen below,
 * at the height of the window. Each column of the screen scrolls on its own, so the page never
 * scrolls as a whole and the action bar stays visible.
 */
import type { ReactNode } from "react";

/** Props of {@link ConsoleShell}. */
export type ConsoleShellProps = {
  readonly appBar: ReactNode;
  /** The screen: the inbox with the selected ticket, or a page of its own. */
  readonly children: ReactNode;
};

/**
 * Render the frame.
 *
 * @param props - The app bar and the screen.
 * @returns The frame at the height of the window.
 */
export function ConsoleShell({ appBar, children }: ConsoleShellProps) {
  return (
    <div className="flex h-screen flex-col">
      {appBar}
      <div className="flex min-h-0 flex-1">{children}</div>
    </div>
  );
}
