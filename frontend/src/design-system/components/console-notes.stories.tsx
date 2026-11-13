import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, fn, userEvent, within } from "storybook/test";

import { KbDocumentText } from "@/design-system/components/kb-document-text";
import { StaffNote } from "@/design-system/components/staff-note";
import { WarningList } from "@/design-system/components/warning-list";

const twoWarnings = [
  { warningId: "w1", title: "Source review overdue", description: "Check that it applies." },
  { warningId: "w2", title: "Intent and sources disagree", description: "Check the intent." },
];

const meta = {
  title: "Design system/Components/WarningList",
  component: WarningList,
  args: {
    warnings: [
      {
        warningId: "w1",
        title: "Missing information",
        description:
          "The request needs information that is in neither the message nor the order. See the note for staff.",
      },
    ],
  },
} satisfies Meta<typeof WarningList>;

export default meta;

type Story = StoryObj<typeof meta>;

export const OneWarning: Story = {};
export const TwoWarnings: Story = { args: { warnings: twoWarnings } };
export const ToAcknowledge: Story = {
  args: { acknowledgedIds: new Set<string>(), onAcknowledgedChange: fn() },
  play: async ({ canvasElement, args }) => {
    await userEvent.click(
      within(canvasElement).getByRole("checkbox", {
        name: "I have checked this warning: Missing information",
      }),
    );

    await expect(args.onAcknowledgedChange).toHaveBeenCalledWith("w1", true);
  },
};
export const OneOfTwoAcknowledged: Story = {
  args: {
    warnings: twoWarnings,
    acknowledgedIds: new Set(["w1"]),
    onAcknowledgedChange: fn(),
  },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);

    await expect(
      canvas.getByRole("checkbox", { name: "I have checked this warning: Source review overdue" }),
    ).toBeChecked();
    await expect(
      canvas.getByRole("checkbox", {
        name: "I have checked this warning: Intent and sources disagree",
      }),
    ).not.toBeChecked();
  },
};
export const StaffNoteText: Story = {
  render: () => (
    <StaffNote>
      The refund has been under review since 14 October. No cited source states how long a review
      takes, so the draft gives no date.
    </StaffNote>
  ),
};
export const KbDocumentWithHighlight: Story = {
  render: () => (
    <KbDocumentText
      body={
        "This is sample text.\nA refund request is reviewed after the returned item is inspected.\nThe rest."
      }
      highlight="A refund request is reviewed after the returned item is inspected."
    />
  ),
};
export const KbDocumentWithoutHighlight: Story = {
  render: () => <KbDocumentText body="This is sample text. It is not KB content." />,
};
