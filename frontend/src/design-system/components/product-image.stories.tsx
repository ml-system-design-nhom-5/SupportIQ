import type { Meta, StoryObj } from "@storybook/react-vite";

import { ProductImage } from "@/design-system/components/product-image";

const meta = {
  title: "Design system/Components/ProductImage",
  component: ProductImage,
  args: { size: "card" },
} satisfies Meta<typeof ProductImage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Card: Story = {};
export const Detail: Story = { args: { size: "detail" } };
export const Thumbnail: Story = { args: { size: "thumbnail" } };
