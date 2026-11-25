import type { Meta, StoryObj } from "@storybook/react-vite";
import { Inbox } from "lucide-react";
import { fn } from "storybook/test";

import { AppBar } from "@/design-system/components/app-bar";
import { CenteredContent } from "@/design-system/components/centered-content";
import { ConsoleShell } from "@/design-system/components/console-shell";
import { InboxItemSkeleton } from "@/design-system/components/inbox-item-skeleton";
import { InboxLayout } from "@/design-system/components/inbox-layout";
import { InboxMessage } from "@/design-system/components/inbox-message";
import { InboxPanel } from "@/design-system/components/inbox-panel";
import { StateMessage } from "@/design-system/components/state-message";
import { TicketHeaderSkeleton } from "@/design-system/components/ticket-header-skeleton";
import { WorkspaceLayout } from "@/design-system/components/workspace-layout";
import { MenuSelect } from "@/design-system/primitives/menu-select";
import { Panel } from "@/design-system/primitives/panel";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Skeleton } from "@/design-system/primitives/skeleton";
import { consoleColumnSizes } from "@/design-system/tokens/column-sizes";

/** The inbox at its default width; the column control stories resize it. */
const inboxColumn = {
  width: consoleColumnSizes.inbox.defaultWidth,
  isCollapsed: false,
  onChange: fn(),
};

/** The AI sidebar at its default width. */
const sidebarColumn = {
  width: consoleColumnSizes.aiDetails.defaultWidth,
  isCollapsed: false,
  onChange: fn(),
};

const meta = {
  title: "Design system/Components/ConsoleShell",
  component: ConsoleShell,
  parameters: { layout: "fullscreen" },
  args: {
    appBar: <AppBar variant="console" brandName="SupportIQ" areaName="Console" />,
    children: (
      <InboxLayout
        inbox={
          <InboxPanel
            statusSelect={
              <MenuSelect
                label="Ticket status"
                options={[{ value: "open", label: "Open" }]}
                value="open"
                onChange={fn()}
              />
            }
            orderLabel="Oldest first"
            onCollapse={fn()}
          >
            <InboxItemSkeleton />
            <InboxItemSkeleton />
          </InboxPanel>
        }
        inboxColumn={inboxColumn}
      >
        <CenteredContent>
          <StateMessage
            icon={Inbox}
            headingLevel={1}
            title="Select a ticket"
            description="Tickets wait in the inbox, oldest first."
          />
        </CenteredContent>
      </InboxLayout>
    ),
  },
} satisfies Meta<typeof ConsoleShell>;

export default meta;

type Story = StoryObj<typeof meta>;

export const NoTicketSelected: Story = {};
export const EmptyInbox: Story = {
  args: {
    children: (
      <InboxLayout
        inbox={
          <InboxPanel statusSelect={<span>Open</span>} orderLabel="Oldest first" onCollapse={fn()}>
            <InboxMessage>
              <p className="text-sm text-text-muted">No open tickets</p>
            </InboxMessage>
          </InboxPanel>
        }
        inboxColumn={inboxColumn}
      >
        <CenteredContent>
          <StateMessage icon={Inbox} headingLevel={1} title="No open tickets" />
        </CenteredContent>
      </InboxLayout>
    ),
  },
};
export const WorkspaceLoading: Story = {
  args: {
    children: (
      <InboxLayout
        inbox={
          <InboxPanel statusSelect={<span>Open</span>} orderLabel="Oldest first" onCollapse={fn()}>
            {null}
          </InboxPanel>
        }
        inboxColumn={inboxColumn}
      >
        <WorkspaceLayout
          header={<TicketHeaderSkeleton />}
          banners={<p className="text-sm">A banner spans the workspace.</p>}
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
          sidebarColumn={sidebarColumn}
        />
      </InboxLayout>
    ),
  },
};
