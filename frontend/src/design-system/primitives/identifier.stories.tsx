import type { Meta, StoryObj } from "@storybook/react-vite";

import { Heading } from "@/design-system/primitives/heading";
import { Identifier } from "@/design-system/primitives/identifier";

const meta = {
  title: "Design system/Primitives/Identifier",
  component: Identifier,
  args: { children: "ORD-20931" },
} satisfies Meta<typeof Identifier>;

export default meta;

type Story = StoryObj<typeof meta>;

export const InText: Story = {};
export const InSecondaryLine: Story = { args: { size: "xs" } };
export const InPageHeading: Story = {
  render: (args) => (
    <Heading level={1}>
      Order <Identifier {...args} />
    </Heading>
  ),
};
