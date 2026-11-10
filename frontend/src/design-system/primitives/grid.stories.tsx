import type { Meta, StoryObj } from "@storybook/react-vite";

import { Grid } from "@/design-system/primitives/grid";
import { Text } from "@/design-system/primitives/text";

const productNames = ["Desk lamp", "Notebook set", "Running shoes", "Wireless headphones"];

const meta = {
  title: "Design system/Primitives/Grid",
  component: Grid,
  args: {
    as: "ul",
    label: "Products",
    children: productNames.map((name) => (
      <li key={name}>
        <Text>{name}</Text>
      </li>
    )),
  },
} satisfies Meta<typeof Grid>;

export default meta;

type Story = StoryObj<typeof meta>;

export const ListOfCells: Story = {};
export const OneCell: Story = {
  args: {
    children: (
      <li>
        <Text>Desk lamp</Text>
      </li>
    ),
  },
};
