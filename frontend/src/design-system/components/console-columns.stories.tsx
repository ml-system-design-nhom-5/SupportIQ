import type { Meta, StoryObj } from "@storybook/react-vite";
import { Info } from "lucide-react";
import { useState } from "react";
import { expect, userEvent, within } from "storybook/test";

import { AppBar } from "@/design-system/components/app-bar";
import type { ColumnRailMark } from "@/design-system/components/column-rail";
import { ConsoleShell } from "@/design-system/components/console-shell";
import { InboxItemSkeleton } from "@/design-system/components/inbox-item-skeleton";
import { InboxLayout } from "@/design-system/components/inbox-layout";
import { InboxPanel } from "@/design-system/components/inbox-panel";
import { TicketHeaderSkeleton } from "@/design-system/components/ticket-header-skeleton";
import { WorkspaceLayout } from "@/design-system/components/workspace-layout";
import { Panel } from "@/design-system/primitives/panel";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Skeleton } from "@/design-system/primitives/skeleton";
import type { ColumnState } from "@/design-system/primitives/use-column-panel";
import { consoleColumnSizes } from "@/design-system/tokens/column-sizes";

const { inbox: inboxSizes, aiDetails, middleMinWidth, railWidth } = consoleColumnSizes;

/** More presses of an arrow key than any column needs to reach its limit. */
const PRESSES_TO_LIMIT = 10;

/** More frames than a layout takes to settle after its group resizes. */
const FRAMES_TO_SETTLE = 10;

/**
 * A console narrower than the window of the stories, where the middle column still has 524 px:
 * 1200 − 272 − 16 for the inbox and its splitter, − 32 − 16 for the workspace padding and the
 * splitter, − 340 for the AI sidebar.
 */
const NARROWER_CONSOLE_WIDTH = 1200;

/** The console at its least width (console UI design, Layout). */
const consoleViewport = {
  console: { name: "Console, 1280 px", styles: { width: "1280", height: "900" } },
};

const meta = {
  title: "Design system/Components/ConsoleColumns",
  component: ConsoleColumns,
  parameters: { layout: "fullscreen", viewport: { options: consoleViewport } },
  globals: { viewport: { value: "console" } },
  args: {
    inbox: { width: inboxSizes.defaultWidth, isCollapsed: false },
    sidebar: { width: aiDetails.defaultWidth, isCollapsed: false },
  },
} satisfies Meta<typeof ConsoleColumns>;

export default meta;

type Story = StoryObj<typeof meta>;

/** Props of {@link ConsoleColumns}. */
type ConsoleColumnsProps = {
  /** The inbox when the story opens. */
  readonly inbox: ColumnState;
  /** The AI sidebar when the story opens. */
  readonly sidebar: ColumnState;
  readonly sidebarMark?: ColumnRailMark;
};

/** The mark of a hidden staff note, as the ticket workspace gives it. */
const staffNoteMark: ColumnRailMark = { label: "Note for staff in AI details", icon: Info };

export const DefaultWidths: Story = {
  play: async ({ canvasElement }) => {
    await expect(columnWidth(canvasElement, "Inbox")).toBe(inboxSizes.defaultWidth);
    await expect(columnWidth(canvasElement, "AI details")).toBe(aiDetails.defaultWidth);
    await expect(middleWidth(canvasElement)).toBeGreaterThanOrEqual(middleMinWidth);
  },
};

export const InboxGrowsToItsMaxWidth: Story = {
  play: async ({ canvasElement }) => {
    within(canvasElement).getByRole("separator", { name: "Resize inbox" }).focus();

    const widths = await pressToLimit(canvasElement, "Inbox", "{ArrowRight}");

    await expect(widths.at(-1)).toBe(inboxSizes.maxWidth);
  },
};

/** The splitter stops at the least width, and a press past it collapses the column. */
export const InboxShrinksToItsMinWidthThenCollapses: Story = {
  play: async ({ canvasElement }) => {
    within(canvasElement).getByRole("separator", { name: "Resize inbox" }).focus();

    const widths = await pressToLimit(canvasElement, "Inbox", "{ArrowLeft}");

    await expect(widths).toContain(inboxSizes.minWidth);
    await expect(new Set(widths.filter((width) => width < inboxSizes.minWidth))).toEqual(
      new Set([railWidth]),
    );
  },
};

export const AiDetailsGrowsUntilTheMiddleColumnIsAtItsLeast: Story = {
  play: async ({ canvasElement }) => {
    within(canvasElement).getByRole("separator", { name: "Resize AI details" }).focus();

    await pressToLimit(canvasElement, "AI details", "{ArrowLeft}");

    await expect(middleWidth(canvasElement)).toBe(middleMinWidth);
  },
};

/** With the inbox collapsed, the middle column has the room for the widest AI sidebar. */
export const AiDetailsGrowsToItsMaxWidth: Story = {
  args: { inbox: { width: inboxSizes.defaultWidth, isCollapsed: true } },
  play: async ({ canvasElement }) => {
    within(canvasElement).getByRole("separator", { name: "Resize AI details" }).focus();

    const widths = await pressToLimit(canvasElement, "AI details", "{ArrowLeft}");

    await expect(widths.at(-1)).toBe(aiDetails.maxWidth);
  },
};

export const AiDetailsShrinksToItsMinWidthThenCollapses: Story = {
  play: async ({ canvasElement }) => {
    within(canvasElement).getByRole("separator", { name: "Resize AI details" }).focus();

    const widths = await pressToLimit(canvasElement, "AI details", "{ArrowRight}");

    await expect(widths).toContain(aiDetails.minWidth);
    await expect(new Set(widths.filter((width) => width < aiDetails.minWidth))).toEqual(
      new Set([railWidth]),
    );
  },
};

export const EnterCollapsesAndRestoresTheInbox: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    canvas.getByRole("separator", { name: "Resize inbox" }).focus();

    await userEvent.keyboard("{Enter}");
    await expect(await canvas.findByRole("button", { name: "Open inbox" })).toBeVisible();
    await expect(columnWidth(canvasElement, "Inbox")).toBe(railWidth);
    await userEvent.keyboard("{Enter}");
    await expect(await canvas.findByRole("button", { name: "Collapse inbox" })).toBeVisible();
    await expect(columnWidth(canvasElement, "Inbox")).toBe(inboxSizes.defaultWidth);
  },
};

export const EnterCollapsesAndRestoresAiDetails: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    canvas.getByRole("separator", { name: "Resize AI details" }).focus();

    await userEvent.keyboard("{Enter}");
    await expect(await canvas.findByRole("button", { name: "Open AI details" })).toBeVisible();
    await expect(columnWidth(canvasElement, "AI details")).toBe(railWidth);
    await userEvent.keyboard("{Enter}");
    await expect(await canvas.findByRole("button", { name: "Collapse AI details" })).toBeVisible();
    await expect(columnWidth(canvasElement, "AI details")).toBe(aiDetails.defaultWidth);
  },
};

export const CollapseButtonsCloseAndOpenTheColumns: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await userEvent.click(canvas.getByRole("button", { name: "Collapse inbox", expanded: true }));
    await nextFrames();
    await userEvent.click(
      canvas.getByRole("button", { name: "Collapse AI details", expanded: true }),
    );
    await nextFrames();
    await expect(columnWidth(canvasElement, "Inbox")).toBe(railWidth);
    await expect(columnWidth(canvasElement, "AI details")).toBe(railWidth);
    await userEvent.click(canvas.getByRole("button", { name: "Open inbox", expanded: false }));
    await nextFrames();
    await userEvent.click(canvas.getByRole("button", { name: "Open AI details", expanded: false }));
    await waitForWidth(canvasElement, "Inbox", inboxSizes.defaultWidth);
    await waitForWidth(canvasElement, "AI details", aiDetails.defaultWidth);
  },
};

/** The width that a splitter gave is the one that the column opens to again. */
export const ReopensAtTheWidthThatTheSplitterGave: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    canvas.getByRole("separator", { name: "Resize inbox" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    await nextFrames();
    const resizedWidth = columnWidth(canvasElement, "Inbox");

    await userEvent.click(canvas.getByRole("button", { name: "Collapse inbox" }));
    await nextFrames();
    await userEvent.click(canvas.getByRole("button", { name: "Open inbox" }));

    await expect(resizedWidth).toBeGreaterThan(inboxSizes.defaultWidth);
    await waitForWidth(canvasElement, "Inbox", resizedWidth);
  },
};

/**
 * A narrower console, then a wider one, as a window that is resized gives: the columns keep their
 * px, and the middle column takes the rest. The story root stands in for the window, which a
 * story cannot resize; it stays within the window, so no scrollbar comes and goes.
 */
export const ColumnsKeepTheirWidthsWhenTheConsoleResizes: Story = {
  play: async ({ canvasElement }) => {
    canvasElement.style.width = `${String(NARROWER_CONSOLE_WIDTH)}px`;
    try {
      await waitForWidth(canvasElement, "Inbox", inboxSizes.defaultWidth);
      await waitForWidth(canvasElement, "AI details", aiDetails.defaultWidth);
    } finally {
      // The stories share the root, so the next story gets it back as it was.
      canvasElement.style.removeProperty("width");
    }

    await waitForWidth(canvasElement, "Inbox", inboxSizes.defaultWidth);
    await waitForWidth(canvasElement, "AI details", aiDetails.defaultWidth);
  },
};

/** The workspace grows when the inbox collapses: the AI sidebar keeps its px. */
export const AiDetailsKeepsItsWidthWhenTheInboxCollapses: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.click(within(canvasElement).getByRole("button", { name: "Collapse inbox" }));

    await waitForWidth(canvasElement, "AI details", aiDetails.defaultWidth);
  },
};

export const BothCollapsed: Story = {
  args: {
    inbox: { width: inboxSizes.defaultWidth, isCollapsed: true },
    sidebar: { width: aiDetails.defaultWidth, isCollapsed: true },
  },
  play: async ({ canvasElement }) => {
    await expect(columnWidth(canvasElement, "Inbox")).toBe(railWidth);
    await expect(columnWidth(canvasElement, "AI details")).toBe(railWidth);
    await expect(
      within(canvasElement).queryByRole("img", { name: staffNoteMark.label }),
    ).not.toBeInTheDocument();
  },
};

export const CollapsedWithStaffNote: Story = {
  args: {
    sidebar: { width: aiDetails.defaultWidth, isCollapsed: true },
    sidebarMark: staffNoteMark,
  },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).getByRole("img", { name: staffNoteMark.label }),
    ).toBeVisible();
  },
};

/**
 * Render the console with both resizable columns, which keep their changes, as the console does.
 *
 * @param props - The inbox and the AI sidebar when the story opens, and the mark of the rail.
 * @returns The console shell with the inbox and a loading workspace.
 */
function ConsoleColumns({ inbox, sidebar, sidebarMark }: ConsoleColumnsProps) {
  const [inboxState, setInboxState] = useState(inbox);
  const [sidebarState, setSidebarState] = useState(sidebar);
  return (
    <ConsoleShell appBar={<AppBar variant="console" brandName="SupportIQ" areaName="Console" />}>
      <InboxLayout
        inbox={
          <InboxPanel
            statusSelect={<span>Open</span>}
            orderLabel="Oldest first"
            onCollapse={() => {
              setInboxState({ ...inboxState, isCollapsed: true });
            }}
          >
            <InboxItemSkeleton />
          </InboxPanel>
        }
        inboxColumn={{ ...inboxState, onChange: setInboxState }}
      >
        <WorkspaceLayout
          header={<TicketHeaderSkeleton />}
          main={
            <Panel density="compact">
              <PanelSection>
                <Skeleton />
              </PanelSection>
            </Panel>
          }
          sidebar={
            <Panel density="compact" tone="ai">
              <PanelSection>
                <Skeleton width="half" />
              </PanelSection>
            </Panel>
          }
          sidebarColumn={{ ...sidebarState, onChange: setSidebarState }}
          sidebarMark={sidebarMark}
        />
      </InboxLayout>
    </ConsoleShell>
  );
}

/**
 * Press a key on the focused splitter more times than any column needs to reach its limit.
 *
 * @param canvasElement - The root element of the story.
 * @param name - The name of the column to measure: "Inbox" or "AI details".
 * @param key - The key, in the notation of user-event.
 * @returns The width of the column after each press.
 */
async function pressToLimit(
  canvasElement: HTMLElement,
  name: string,
  key: string,
): Promise<number[]> {
  const widths: number[] = [];
  for (let press = 0; press < PRESSES_TO_LIMIT; press += 1) {
    await userEvent.keyboard(key);
    widths.push(columnWidth(canvasElement, name));
  }
  return widths;
}

/**
 * Measure a resizable column.
 *
 * @param canvasElement - The root element of the story.
 * @param name - The name of the column: "Inbox", a navigation landmark, or "AI details", a
 *   region.
 * @returns The width of its panel in whole px, as the layout keeps it.
 */
function columnWidth(canvasElement: HTMLElement, name: string): number {
  const canvas = within(canvasElement);
  const column = canvas.queryByRole("navigation", { name }) ?? canvas.getByRole("region", { name });
  return Math.round(panelOf(column).getBoundingClientRect().width);
}

/**
 * Let two frames pass, as they do between two actions of a person: the layout keeps a change of
 * the splitter on the frame after it, and the splitter library resizes a group on a frame of its
 * own. User-event acts faster than any person, within one frame.
 */
async function nextFrames(): Promise<void> {
  for (let frame = 0; frame < 2; frame += 1) {
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }
}

/**
 * Wait until a column has a width, which the layout reaches on a later frame when the browser
 * resizes its group, and record the check.
 *
 * @param canvasElement - The root element of the story.
 * @param name - The name of the column: "Inbox" or "AI details".
 * @param width - The width in px.
 * @returns A promise that settles when the check is recorded.
 */
async function waitForWidth(
  canvasElement: HTMLElement,
  name: string,
  width: number,
): Promise<void> {
  for (
    let frame = 0;
    frame < FRAMES_TO_SETTLE && columnWidth(canvasElement, name) !== width;
    frame += 1
  ) {
    await new Promise((resolve) => requestAnimationFrame(resolve));
  }
  await expect(columnWidth(canvasElement, name)).toBe(width);
}

/**
 * Measure the middle column of the workspace.
 *
 * @param canvasElement - The root element of the story.
 * @returns Its width in px.
 */
function middleWidth(canvasElement: HTMLElement): number {
  const header = within(canvasElement).getByRole("separator", { name: "Resize AI details" });
  const middle = header.previousElementSibling;
  if (middle === null) {
    throw new Error("The middle column is missing.");
  }
  return middle.getBoundingClientRect().width;
}

/**
 * Find the panel of the splitter library that holds a column.
 *
 * @param element - An element inside the panel.
 * @returns The panel.
 */
function panelOf(element: HTMLElement): Element {
  const panel = element.closest("[data-panel]");
  if (panel === null) {
    throw new Error("The column is not inside a panel.");
  }
  return panel;
}
