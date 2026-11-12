/**
 * The ticket workspace (console UI design, Layout and placement rules): the ticket header and the
 * banners span the full width; below them, the middle column holds the customer message, the
 * intent, and the reply area, and the right column, 340 px wide, holds the AI sidebar. Each column
 * scrolls on its own.
 */
import type { ReactNode } from "react";

/** Props of {@link WorkspaceLayout}. */
export type WorkspaceLayoutProps = {
  readonly header: ReactNode;
  /** The banners, such as Authority required; absent when there are none. */
  readonly banners?: ReactNode;
  readonly main: ReactNode;
  readonly sidebar: ReactNode;
};

/**
 * Render the workspace.
 *
 * @param props - The header, the banners, the middle column, and the AI sidebar.
 * @returns The workspace, filling the space next to the inbox.
 */
export function WorkspaceLayout({ header, banners, main, sidebar }: WorkspaceLayoutProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {header}
      {banners === undefined ? null : (
        <div className="flex flex-col gap-2 px-4 pt-4">{banners}</div>
      )}
      <div className="flex min-h-0 flex-1 gap-4 p-4">
        <div className="flex min-w-0 flex-1 flex-col gap-4 overflow-y-auto">{main}</div>
        <section
          aria-label="AI sidebar"
          className="flex w-ai-sidebar shrink-0 flex-col gap-4 overflow-y-auto"
        >
          {sidebar}
        </section>
      </div>
    </div>
  );
}
