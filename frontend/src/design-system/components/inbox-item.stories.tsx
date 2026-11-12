import type { Meta, StoryObj } from "@storybook/react-vite";

import { ConfidenceMeter } from "@/design-system/components/confidence-meter";
import { InboxItem } from "@/design-system/components/inbox-item";
import { InboxItemSkeleton } from "@/design-system/components/inbox-item-skeleton";
import {
  presentationByAiStatus,
  presentationByConsoleTicketStatus,
} from "@/design-system/components/status-presentations";

const meta = {
  title: "Design system/Components/InboxItem",
  component: InboxItem,
  args: {
    to: "/console/tickets/TCK-1042",
    ticketId: "TCK-1042",
    createdAt: "2026-11-05T08:42:00Z",
    customerName: "Linh Tran",
    excerpt:
      "Hi, I sent back the headphones from order ORD-20931 almost two weeks ago and I still haven't got my money back.",
    intentLine: (
      <>
        Refund status
        <ConfidenceMeter band="high" probability={0.91} />
      </>
    ),
    status: presentationByAiStatus.draft_ready,
    isAuthorityRequired: false,
  },
  decorators: [
    (Story) => (
      <ul className="flex w-inbox flex-col bg-surface">
        <Story />
      </ul>
    ),
  ],
} satisfies Meta<typeof InboxItem>;

export default meta;

type Story = StoryObj<typeof meta>;

export const DraftReady: Story = {};
export const OpenedByAColleague: Story = { args: { openedAt: "2026-11-05T08:56:00Z" } };
export const AuthorityRequired: Story = {
  args: { status: presentationByAiStatus.draft_ready, isAuthorityRequired: true },
};
export const LowConfidence: Story = {
  args: {
    intentLine: (
      <>
        Cancel order
        <ConfidenceMeter band="low" probability={0.41} />
      </>
    ),
    status: presentationByAiStatus.abstained,
  },
};
export const NoAnalysis: Story = {
  args: {
    intentLine: <span className="text-text-muted">No analysis</span>,
    status: presentationByAiStatus.unavailable,
  },
};
export const Closed: Story = { args: { status: presentationByConsoleTicketStatus.closed } };
export const Loading: Story = { render: () => <InboxItemSkeleton /> };
