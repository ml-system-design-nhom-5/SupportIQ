import type { Meta, StoryObj } from "@storybook/react-vite";
import type { ReactNode } from "react";

import { ConfidenceMeter } from "@/design-system/components/confidence-meter";
import { InboxItem } from "@/design-system/components/inbox-item";
import { InboxItemSkeleton } from "@/design-system/components/inbox-item-skeleton";
import { StatusBadge } from "@/design-system/components/status-badge";
import {
  authorityRequiredPresentation,
  presentationByAiStatus,
  presentationByConsoleTicketStatus,
  type StatusPresentation,
} from "@/design-system/components/status-presentations";
import { Cluster } from "@/design-system/primitives/cluster";
import { Stack } from "@/design-system/primitives/stack";
import { Text } from "@/design-system/primitives/text";

/**
 * Build the details of an item: its intent line and its badges.
 *
 * @param props - The intent line, the status, and whether authority is required.
 * @returns The details.
 */
function Details({
  intentLine,
  status,
  isAuthorityRequired = false,
}: {
  readonly intentLine: ReactNode;
  readonly status: StatusPresentation;
  readonly isAuthorityRequired?: boolean;
}) {
  return (
    <>
      <Stack direction="row" gap="2" align="center">
        {intentLine}
      </Stack>
      <Cluster>
        <StatusBadge presentation={status} />
        {isAuthorityRequired ? <StatusBadge presentation={authorityRequiredPresentation} /> : null}
      </Cluster>
    </>
  );
}

const refundStatusLine = (
  <>
    Refund status
    <ConfidenceMeter band="high" probability={0.91} />
  </>
);

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
    children: <Details intentLine={refundStatusLine} status={presentationByAiStatus.draft_ready} />,
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
  args: {
    children: (
      <Details
        intentLine={refundStatusLine}
        status={presentationByAiStatus.draft_ready}
        isAuthorityRequired
      />
    ),
  },
};
export const LowConfidence: Story = {
  args: {
    children: (
      <Details
        intentLine={
          <>
            Cancel order
            <ConfidenceMeter band="low" probability={0.41} />
          </>
        }
        status={presentationByAiStatus.abstained}
      />
    ),
  },
};
export const NoAnalysis: Story = {
  args: {
    children: (
      <Details
        intentLine={<Text tone="muted">No analysis</Text>}
        status={presentationByAiStatus.unavailable}
      />
    ),
  },
};
export const Closed: Story = {
  args: {
    children: (
      <Details intentLine={refundStatusLine} status={presentationByConsoleTicketStatus.closed} />
    ),
  },
};
export const Loading: Story = { render: () => <InboxItemSkeleton /> };
