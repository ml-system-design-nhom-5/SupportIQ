import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, screen, userEvent, within } from "storybook/test";

import { CitationMarker } from "@/design-system/components/citation-marker";
import { DraftText } from "@/design-system/components/draft-text";
import { MarkedText } from "@/design-system/components/marked-text";
import { OrderCitationMarker } from "@/design-system/components/order-citation-marker";
import { presentationByDocumentValidity } from "@/design-system/components/status-presentations";

const meta = {
  title: "Design system/Components/DraftText",
  component: DraftText,
  args: {
    paragraphs: [
      {
        paragraphId: "p0",
        segments: [{ segmentId: "s1", text: "Thank you for your patience." }],
      },
      {
        paragraphId: "p1",
        segments: [
          {
            segmentId: "s2",
            text: "Your refund request for order ORD-20931 is under review.",
            markers: (
              <OrderCitationMarker
                orderId="ORD-20931"
                facts={[{ term: "Refund status", value: "Refund under review" }]}
                onActivate={fn()}
              />
            ),
          },
          {
            segmentId: "s3",
            text: "Refund requests are reviewed as described in our refund policy.",
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
                snippet="A refund request is reviewed after the returned item is inspected."
                onActivate={fn()}
              />
            ),
          },
        ],
      },
    ],
  },
} satisfies Meta<typeof DraftText>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithCitations: Story = {};
export const KbMarkerFocused: Story = {
  play: async ({ canvasElement }) => {
    await userEvent.tab();
    await userEvent.tab();
    await expect(
      within(canvasElement).getByRole("button", { name: "Source 1: Refund policy" }),
    ).toHaveFocus();

    await expect(
      await screen.findByText(
        "“A refund request is reviewed after the returned item is inspected.”",
      ),
    ).toBeVisible();
  },
};
export const OrderMarkerFocused: Story = {
  play: async () => {
    await userEvent.tab();

    await expect(await screen.findAllByText("From order records, not AI")).not.toHaveLength(0);
  },
};
export const RejectedOrOutdated: Story = { args: { tone: "muted" } };
export const WithPlaceholder: Story = {
  args: {
    paragraphs: [
      {
        paragraphId: "p0",
        segments: [
          {
            segmentId: "s1",
            text: (
              <MarkedText
                parts={[
                  { text: "We have sent the return label to ", isMarked: false },
                  { text: "[EMAIL]", isMarked: true },
                  { text: ".", isMarked: false },
                ]}
              />
            ),
          },
        ],
      },
    ],
  },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByText("[EMAIL]").tagName).toBe("MARK");
  },
};
export const KbSourceWithoutAnalysis: Story = {
  args: {
    paragraphs: [
      {
        paragraphId: "p0",
        segments: [
          {
            segmentId: "s1",
            text: "A sentence that cites a version that the analysis did not return.",
            markers: (
              <CitationMarker
                number={2}
                source={{ title: "DOC-9", documentId: "DOC-9", version: "1" }}
                snippet="A passage."
                onActivate={fn()}
              />
            ),
          },
        ],
      },
    ],
  },
};
