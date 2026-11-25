import type { Meta, StoryObj } from "@storybook/react-vite";

import { ProductCard } from "@/design-system/components/product-card";
import { ProductCardSkeleton } from "@/design-system/components/product-card-skeleton";
import { Grid } from "@/design-system/primitives/grid";
import { expectNoSidewaysOverflow } from "@/test/story-checks";

const meta = {
  title: "Design system/Shop/ProductCard",
  component: ProductCard,
  decorators: [
    (Story) => (
      <Grid as="ul" label="Products">
        <Story />
      </Grid>
    ),
  ],
  args: {
    name: "Wireless headphones",
    category: "Audio",
    price: { amountMinor: 8900, currency: "USD" },
    href: "/shop/products/PRD-1002",
  },
} satisfies Meta<typeof ProductCard>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const LongUnbrokenName: Story = {
  args: { name: "N".repeat(160), category: "C".repeat(160) },
  play: ({ canvasElement }) => expectNoSidewaysOverflow(canvasElement),
};
export const LongNonAsciiName: Story = {
  args: { name: "Tai nghe không dây chống ồn chủ động thế hệ thứ hai, phiên bản đặc biệt" },
};
export const Loading: Story = { render: () => <ProductCardSkeleton /> };
