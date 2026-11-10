import type { Meta, StoryObj } from "@storybook/react-vite";

import { PageColumn } from "@/design-system/primitives/page-column";
import { Text } from "@/design-system/primitives/text";

const meta = {
  title: "Design system/Primitives/PageColumn",
  component: PageColumn,
  parameters: { layout: "fullscreen" },
  args: { area: "shop", children: <Text size="base">The content of the screen.</Text> },
} satisfies Meta<typeof PageColumn>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Shop: Story = {};
export const Admin: Story = { args: { area: "admin" } };
