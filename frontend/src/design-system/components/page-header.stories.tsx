import type { Meta, StoryObj } from "@storybook/react-vite";
import { MessageSquare } from "lucide-react";

import { PageHeader } from "@/design-system/components/page-header";
import { Button } from "@/design-system/primitives/button";
import { Text } from "@/design-system/primitives/text";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const meta = {
  title: "Design system/Components/PageHeader",
  component: PageHeader,
  args: { title: "My orders" },
} satisfies Meta<typeof PageHeader>;

export default meta;

type Story = StoryObj<typeof meta>;

export const TitleOnly: Story = {};
export const LongUnbrokenTitle: Story = {
  args: { title: "N".repeat(160) },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
export const Compact: Story = {
  args: {
    title: "Accounts",
    density: "compact",
    action: <Text tone="muted">Internal accounts only.</Text>,
  },
};
export const WithMeta: Story = {
  args: { title: "Products", meta: "A read-only catalog for the demo" },
};
export const WithAction: Story = {
  args: {
    title: "Order ORD-20931",
    meta: "Placed 2 Oct 2026",
    action: (
      <Button size="lg" width="full-on-phone" leadingIcon={MessageSquare}>
        Contact support
      </Button>
    ),
  },
};
