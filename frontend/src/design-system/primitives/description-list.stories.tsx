import type { Meta, StoryObj } from "@storybook/react-vite";

import { DescriptionList } from "@/design-system/primitives/description-list";

const meta = {
  title: "Design system/Primitives/DescriptionList",
  component: DescriptionList,
  args: {
    items: [
      { term: "In effect", description: "1 Jan 2026 to 1 Jan 2027" },
      { term: "Owner", description: "Policy owner (sample)" },
      { term: "Source", description: "Sample source document" },
    ],
  },
} satisfies Meta<typeof DescriptionList>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
