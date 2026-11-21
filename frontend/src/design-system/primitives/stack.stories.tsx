import type { Meta, StoryObj } from "@storybook/react-vite";

import { Stack } from "@/design-system/primitives/stack";
import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Primitives/Stack",
  component: Stack,
  args: {
    gap: "4",
    children: (
      <>
        <Text>Order</Text>
        <Text>Shipment</Text>
        <Text>Refund</Text>
      </>
    ),
  },
} satisfies Meta<typeof Stack>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Column: Story = {};
export const Row: Story = { args: { direction: "row", align: "center" } };
export const RowSpacedBetween: Story = { args: { direction: "row", justify: "between" } };
export const NamedSection: Story = { args: { as: "section", label: "Order statuses" } };
