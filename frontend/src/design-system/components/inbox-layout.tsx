/**
 * The inbox on the left, 272 px wide, and the selected ticket on the right (console UI design,
 * Layout). The inbox is a complementary landmark; the ticket is the `main` landmark.
 */
import type { ReactNode } from "react";

/** Props of {@link InboxLayout}. */
export type InboxLayoutProps = {
  readonly inbox: ReactNode;
  /** The workspace of the selected ticket, or the prompt to select one. */
  readonly children: ReactNode;
};

/**
 * Render the inbox next to the selected ticket.
 *
 * @param props - The inbox and the selected ticket.
 * @returns The two columns.
 */
export function InboxLayout({ inbox, children }: InboxLayoutProps) {
  return (
    <>
      <aside
        aria-label="Inbox"
        className="flex w-inbox shrink-0 flex-col border-r border-border bg-surface"
      >
        {inbox}
      </aside>
      <main className="flex min-w-0 flex-1 flex-col">{children}</main>
    </>
  );
}
