import type { Meta, StoryObj } from "@storybook/react-vite";

import { RowList } from "@/design-system/components/row-list";
import { RowListItem } from "@/design-system/components/row-list-item";
import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Components/RowList",
  component: RowList,
  args: {
    label: "Your orders",
    children: (
      <>
        <RowListItem to="/shop/orders/ORD-20990" trailing={<Text size="lg">$42.50</Text>}>
          <Text size="base">Order ORD-20990</Text>
          <Text tone="muted">Desk lamp, Notebook set × 2</Text>
        </RowListItem>
        <RowListItem to="/shop/orders/ORD-20955" trailing={<Text size="lg">$64.00</Text>}>
          <Text size="base">Order ORD-20955</Text>
          <Text tone="muted">Running shoes</Text>
        </RowListItem>
      </>
    ),
  },
} satisfies Meta<typeof RowList>;

export default meta;

type Story = StoryObj<typeof meta>;

export const TwoRows: Story = {};
export const TrailingBelowAtPhoneWidth: Story = {
  args: {
    children: (
      <RowListItem
        to="/shop/orders/ORD-20931"
        trailing={<Text>Received</Text>}
        trailingOnPhone="below"
      >
        <Text size="base" overflow="truncate">
          I asked for a refund for the headphones three weeks ago. When will it be paid?
        </Text>
      </RowListItem>
    ),
  },
};
export const OneRowWithoutTrailing: Story = {
  args: {
    children: (
      <RowListItem to="/shop/orders/ORD-20931">
        <Text size="base">Where is my parcel?</Text>
      </RowListItem>
    ),
  },
};
