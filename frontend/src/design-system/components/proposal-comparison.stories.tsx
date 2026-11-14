import type { Meta, StoryObj } from "@storybook/react-vite";
import { Clock } from "lucide-react";
import { expect, fn, within } from "storybook/test";

import { CitationMarker } from "@/design-system/components/citation-marker";
import { DraftText } from "@/design-system/components/draft-text";
import { ProposalComparison } from "@/design-system/components/proposal-comparison";
import { presentationByDocumentValidity } from "@/design-system/components/status-presentations";
import { Panel } from "@/design-system/primitives/panel";
import { PanelHeader } from "@/design-system/primitives/panel-header";
import { PanelSection } from "@/design-system/primitives/panel-section";
import { Text } from "@/design-system/primitives/text";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const proposalText =
  "Hi An, I'm sorry your blender arrived damaged. I have passed your refund request to a manager, who will decide on it and reply to you here.";

const longProposalText = Array.from(
  { length: 4 },
  () =>
    "Hi An, I'm sorry your blender arrived damaged. I have passed your refund request to a manager, who will read the order details and your message, decide on it, and reply to you on this ticket.",
).join("\n\n");

const meta = {
  title: "Design system/Components/ProposalComparison",
  component: ProposalComparison,
  args: {
    proposal: {
      authorName: "Minh Le (staff)",
      submittedAt: "2026-11-05T08:48:00Z",
      content: <Text overflow="preserve">{proposalText}</Text>,
    },
    aiDraft: (
      <DraftText
        paragraphs={[
          {
            paragraphId: "p0",
            segments: [
              { segmentId: "s1", text: "I'm sorry the blender arrived with a cracked jug." },
            ],
          },
          {
            paragraphId: "p1",
            segments: [
              {
                segmentId: "s2",
                text: "Refund requests for items that arrive damaged are handled under our refund policy.",
                markers: (
                  <CitationMarker
                    number={1}
                    source={{
                      title: "Refund policy",
                      documentId: "refund-policy",
                      version: "v3",
                      validity: presentationByDocumentValidity.valid,
                      period: "Since 1 Sept 2026",
                    }}
                    snippet="This is sample text, not KB content."
                    onActivate={fn()}
                  />
                ),
              },
              {
                segmentId: "s3",
                text: "A manager will review your request and reply to you on this ticket.",
              },
            ],
          },
        ]}
      />
    ),
  },
  // The reply area of the console holds the comparison under its level 2 heading.
  decorators: [
    (Story) => (
      <Panel as="section" label="Reply for approval" density="compact">
        <PanelHeader icon={Clock} level={2} title="Reply for approval" />
        <PanelSection>
          <Story />
        </PanelSection>
      </Panel>
    ),
  ],
} satisfies Meta<typeof ProposalComparison>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ManagerView: Story = {
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(canvas.getByRole("region", { name: "Staff proposal" })).toBeVisible();
    await expect(canvas.getByRole("region", { name: "AI draft for comparison" })).toBeVisible();
  },
};
export const WithoutAiDraft: Story = {
  args: { aiDraft: undefined },
  play: async ({ canvasElement }) => {
    await expect(
      within(canvasElement).queryByRole("region", { name: "AI draft for comparison" }),
    ).not.toBeInTheDocument();
  },
};
export const LongProposal: Story = {
  args: {
    proposal: {
      authorName: "Mai Nguyen (you)",
      submittedAt: "2026-11-05T08:58:00Z",
      content: <Text overflow="preserve">{longProposalText}</Text>,
    },
  },
  play: async ({ canvasElement }) => {
    await expectNoSidewaysOverflow(canvasElement);
  },
};
