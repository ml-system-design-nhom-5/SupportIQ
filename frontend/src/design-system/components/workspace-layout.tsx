/**
 * The ticket workspace (console UI design, Layout, Column controls, and placement rules): the
 * ticket header and the banners span the full width; below them, the middle column holds the
 * customer message, the intent, and the reply area, and the right column holds the AI sidebar
 * under its header "AI details". A splitter resizes the AI sidebar within its limits in px, and
 * the middle column keeps its least width; a collapsed AI sidebar keeps a 48 px rail with the
 * marks of what it hides. The AI sidebar keeps its width when the window grows, so the middle
 * column takes the rest. Each column scrolls on its own.
 */
import { PanelRightClose, PanelRightOpen, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { Group, Panel } from "react-resizable-panels";

import { ColumnRail, type ColumnRailMark } from "@/design-system/components/column-rail";
import { ColumnSeparator } from "@/design-system/primitives/column-separator";
import { Icon } from "@/design-system/primitives/icon";
import { IconButton } from "@/design-system/primitives/icon-button";
import { type ResizableColumn, useColumnPanel } from "@/design-system/primitives/use-column-panel";
import { consoleColumnSizes } from "@/design-system/tokens/column-sizes";

const { aiDetails, railWidth } = consoleColumnSizes;

/** Props of {@link WorkspaceLayout}. */
export type WorkspaceLayoutProps = {
  readonly header: ReactNode;
  /** The banners, such as Authority required; absent when there are none. */
  readonly banners?: ReactNode;
  readonly main: ReactNode;
  readonly sidebar: ReactNode;
  /** The width of the AI sidebar, whether it is collapsed, and the handler of their changes. */
  readonly sidebarColumn: ResizableColumn;
  /** What the rail of the collapsed AI sidebar marks, such as a staff note; absent, or undefined,
   *  for none. */
  readonly sidebarMark?: ColumnRailMark | undefined;
};

/**
 * Render the workspace.
 *
 * @param props - The header, the banners, the middle column, the AI sidebar, its column, and the
 *   mark of its rail.
 * @returns The workspace, filling the space next to the inbox.
 */
export function WorkspaceLayout({
  header,
  banners,
  main,
  sidebar,
  sidebarColumn,
  sidebarMark,
}: WorkspaceLayoutProps) {
  const { panelRef, reportLayout } = useColumnPanel(sidebarColumn);
  const setIsCollapsed = (isCollapsed: boolean) => {
    sidebarColumn.onChange({ width: sidebarColumn.width, isCollapsed });
  };
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {header}
      {banners === undefined ? null : (
        <div className="flex flex-col gap-2 px-4 pt-4">{banners}</div>
      )}
      <Group className="flex min-h-0 flex-1 p-4" onLayoutChanged={reportLayout}>
        <Panel
          id="middle"
          minSize={consoleColumnSizes.middleMinWidth}
          className="flex min-w-0 flex-col gap-4 overflow-y-auto"
        >
          {main}
        </Panel>
        <ColumnSeparator
          label="Resize AI details"
          onKeyDown={(event) => {
            // The library collapses only the column before a splitter; Enter here is for the AI
            // sidebar after it (console UI design, Column controls).
            if (event.key === "Enter") {
              setIsCollapsed(!sidebarColumn.isCollapsed);
            }
          }}
        />
        <Panel
          id="ai-details"
          panelRef={panelRef}
          defaultSize={sidebarColumn.isCollapsed ? railWidth : sidebarColumn.width}
          minSize={aiDetails.minWidth}
          maxSize={aiDetails.maxWidth}
          collapsible
          collapsedSize={railWidth}
          groupResizeBehavior="preserve-pixel-size"
          className="flex flex-col"
        >
          <section
            aria-label="AI details"
            className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto"
          >
            {sidebarColumn.isCollapsed ? (
              <ColumnRail
                openLabel="Open AI details"
                openIcon={PanelRightOpen}
                icon={Sparkles}
                mark={sidebarMark}
                onOpen={() => {
                  setIsCollapsed(false);
                }}
              />
            ) : (
              <>
                {/* A label, not a heading: the panels of the sidebar are level-2 headings, like
                    those of the middle column. PanelHeader draws a panel header, not this label. */}
                <div className="flex items-center gap-2 text-xs font-semibold text-text-muted">
                  <Icon icon={Sparkles} size="sm" />
                  AI details
                  <span className="ml-auto">
                    <IconButton
                      label="Collapse AI details"
                      icon={PanelRightClose}
                      isExpanded
                      onClick={() => {
                        setIsCollapsed(true);
                      }}
                    />
                  </span>
                </div>
                {sidebar}
              </>
            )}
          </section>
        </Panel>
      </Group>
    </div>
  );
}
