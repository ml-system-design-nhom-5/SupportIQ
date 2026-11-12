import type { Meta, StoryObj } from "@storybook/react-vite";

import { KbDocumentText } from "@/design-system/components/kb-document-text";
import { StaffNote } from "@/design-system/components/staff-note";
import { WarningList } from "@/design-system/components/warning-list";

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
export const TwoWarnings: Story = {
  args: {
    warnings: [
      { warningId: "w1", title: "Source review overdue", description: "Check that it applies." },
      { warningId: "w2", title: "Intent and sources disagree", description: "Check the intent." },
    ],
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
