import type { Meta, StoryObj } from "@storybook/react-vite";
import { fn } from "storybook/test";

import { SourceList } from "@/design-system/components/source-list";
import { presentationByDocumentValidity } from "@/design-system/components/status-presentations";

const meta = {
  title: "Design system/Components/SourceList",
  component: SourceList,
  args: {
    sources: [
      {
        key: "refund-policy v3",
        number: 1,
        title: "Refund policy",
        documentId: "refund-policy",
        version: "v3",
        validity: presentationByDocumentValidity.valid,
        period: "Since 1 Sept 2026",
      },
      {
        key: "returns-policy v2",
        number: 2,
        title: "Returns policy",
        documentId: "returns-policy",
        version: "v2",
        validity: presentationByDocumentValidity.conflicting,
        period: "Since 15 Jul 2026",
      },
      {
        key: "shipping-faq v4",
        title: "Shipping FAQ",
        documentId: "shipping-faq",
        version: "v4",
        validity: presentationByDocumentValidity.expired,
        period: "Ended 30 Sept 2026",
      },
    ],
    onOpen: fn(),
  },
  decorators: [
    (Story) => (
      <div className="w-ai-sidebar">
        <Story />
      </div>
    ),
  ],
} satisfies Meta<typeof SourceList>;

export default meta;

type Story = StoryObj<typeof meta>;

export const CitedAndNotCited: Story = {};
