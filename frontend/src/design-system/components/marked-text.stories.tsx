import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect, within } from "storybook/test";

import { MarkedText } from "@/design-system/components/marked-text";

const meta = {
  title: "Design system/Components/MarkedText",
  component: MarkedText,
  args: {
    parts: [
      { text: "We have sent the return label to ", isMarked: false },
      { text: "[EMAIL]", isMarked: true },
      { text: ". Please reply with the tracking number of ", isMarked: false },
      { text: "[ORDER_ID_1]", isMarked: true },
      { text: ".", isMarked: false },
    ],
  },
  render: (args) => (
    <p className="text-sm text-text">
      <MarkedText {...args} />
    </p>
  ),
} satisfies Meta<typeof MarkedText>;

export default meta;

type Story = StoryObj<typeof meta>;

export const WithMarks: Story = {
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getByText("[EMAIL]").tagName).toBe("MARK");
  },
};
export const WithoutMarks: Story = {
  args: { parts: [{ text: "Thank you for your patience.", isMarked: false }] },
};
export const BackdropLayer: Story = { args: { layer: "backdrop" } };
export const SamePlaceholderTwice: Story = {
  args: {
    parts: [
      { text: "[NAME]", isMarked: true },
      { text: " and ", isMarked: false },
      { text: "[NAME]", isMarked: true },
    ],
  },
  play: async ({ canvasElement }) => {
    await expect(within(canvasElement).getAllByText("[NAME]")).toHaveLength(2);
  },
};
