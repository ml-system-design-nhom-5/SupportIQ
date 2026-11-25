/**
 * The inbox on the left and the selected ticket on the right (console UI design, Layout and
 * Column controls). The `main` landmark holds both: the inbox is a navigation landmark of links
 * to tickets, and the splitter between the columns sits inside `main`, as axe requires of every
 * content (rule `region`); an `aside` would have to stand outside `main`, and the splitter with
 * it. The splitter resizes the inbox within its limits in px, and a collapsed inbox keeps a 48 px
 * rail. The inbox keeps its width when the window grows, so the ticket takes the rest.
 */
import { Inbox, PanelLeftOpen } from "lucide-react";
import type { ReactNode } from "react";
import { Group, Panel } from "react-resizable-panels";

import { ColumnRail } from "@/design-system/components/column-rail";
import { ColumnSeparator } from "@/design-system/primitives/column-separator";
import { type ResizableColumn, useColumnPanel } from "@/design-system/primitives/use-column-panel";
import { consoleColumnSizes } from "@/design-system/tokens/column-sizes";

const {
  inbox: inboxSizes,
  aiDetails,
  railWidth,
  separatorWidth,
  workspacePadding,
} = consoleColumnSizes;

/**
 * The least width of the ticket: the middle column at its least, the AI sidebar at its least,
 * the splitter between them, and the padding of the workspace. So the inbox splitter stops before
 * the middle column gets narrower than its least width.
 */
const TICKET_MIN_WIDTH =
  consoleColumnSizes.middleMinWidth + aiDetails.minWidth + separatorWidth + workspacePadding;

/** Props of {@link InboxLayout}. */
export type InboxLayoutProps = {
  readonly inbox: ReactNode;
  /** The width of the inbox, whether it is collapsed, and the handler of their changes. */
  readonly inboxColumn: ResizableColumn;
  /** The workspace of the selected ticket, or the prompt to select one. */
  readonly children: ReactNode;
};

/**
 * Render the inbox next to the selected ticket.
 *
 * @param props - The inbox, its column, and the selected ticket.
 * @returns The two columns and the splitter.
 */
export function InboxLayout({ inbox, inboxColumn, children }: InboxLayoutProps) {
  const { panelRef, reportLayout } = useColumnPanel(inboxColumn);
  return (
    <main className="flex min-h-0 min-w-0 flex-1">
      <Group className="flex min-w-0 flex-1" onLayoutChanged={reportLayout}>
        <Panel
          id="inbox"
          panelRef={panelRef}
          defaultSize={inboxColumn.isCollapsed ? railWidth : inboxColumn.width}
          minSize={inboxSizes.minWidth}
          maxSize={inboxSizes.maxWidth}
          collapsible
          collapsedSize={railWidth}
          groupResizeBehavior="preserve-pixel-size"
          className="flex flex-col border-r border-border bg-surface"
        >
          <nav aria-label="Inbox" className="flex min-h-0 flex-1 flex-col">
            {inboxColumn.isCollapsed ? (
              <ColumnRail
                openLabel="Open inbox"
                openIcon={PanelLeftOpen}
                icon={Inbox}
                onOpen={() => {
                  inboxColumn.onChange({ width: inboxColumn.width, isCollapsed: false });
                }}
              />
            ) : (
              inbox
            )}
          </nav>
        </Panel>
        <ColumnSeparator label="Resize inbox" />
        <Panel id="ticket" minSize={TICKET_MIN_WIDTH} className="flex min-w-0 flex-col">
          <div className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</div>
        </Panel>
      </Group>
    </main>
  );
}
