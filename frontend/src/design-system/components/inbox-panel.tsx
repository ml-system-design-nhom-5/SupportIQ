/**
 * The content of the inbox column (console UI design, Inbox): a header with the status dropdown
 * and the order of the queue, and the tickets below it, which scroll on their own.
 */
import { Inbox } from "lucide-react";
import type { ReactNode } from "react";

import { Icon } from "@/design-system/primitives/icon";

/** Props of {@link InboxPanel}. */
export type InboxPanelProps = {
  /** The dropdown that selects the queue. */
  readonly statusSelect: ReactNode;
  /** The order of the queue, for example "Oldest first". */
  readonly orderLabel: string;
  /** The tickets, or the loading, empty, or error state of the queue. */
  readonly children: ReactNode;
};

/**
 * Render the inbox.
 *
 * @param props - The dropdown, the order, and the tickets.
 * @returns The header and the scrolling list.
 */
export function InboxPanel({ statusSelect, orderLabel, children }: InboxPanelProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <Icon icon={Inbox} tone="muted" />
        {statusSelect}
        <span className="ml-auto text-sm text-text-muted">{orderLabel}</span>
      </div>
      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</div>
    </div>
  );
}
