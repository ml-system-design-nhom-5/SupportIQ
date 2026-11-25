import type { Meta, StoryObj } from "@storybook/react-vite";

import { presentationByAiReasonCode } from "@/design-system/components/ai-presentations";
import { StatusBadge } from "@/design-system/components/status-badge";
import { Cluster } from "@/design-system/primitives/cluster";

const meta = {
  title: "Design system/Primitives/Cluster",
  component: Cluster,
  args: {
    children: (
      <>
        <StatusBadge presentation={presentationByAiReasonCode.missing_information} />
        <StatusBadge presentation={presentationByAiReasonCode.requires_authority} />
        <StatusBadge presentation={presentationByAiReasonCode.conflicting_sources} />
        <StatusBadge presentation={presentationByAiReasonCode.source_review_overdue} />
      </>
    ),
  },
} satisfies Meta<typeof Cluster>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Badges: Story = {};
export const WrappedInANarrowColumn: Story = {
  decorators: [
    (Story) => (
      <div className="w-inbox">
        <Story />
      </div>
    ),
  ],
};
