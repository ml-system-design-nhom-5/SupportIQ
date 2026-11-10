import type { Meta, StoryObj } from "@storybook/react-vite";

import { ProductPage } from "@/features/shop-catalog/components/product-page";
import { getShopProductRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Shop/Product",
  component: ProductPage,
  args: { productId: "PRD-1002" },
} satisfies Meta<typeof ProductPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const Found: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopProductRoute, exampleAnswer(200, "getShopProduct", "found"));
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopProductRoute, { kind: "no_answer" });
    }),
  ],
};

export const NotFound: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopProductRoute, exampleAnswer(404, "problems", "not-found"));
    }),
  ],
};

export const PermissionDenied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopProductRoute, exampleAnswer(403, "problems", "forbidden-role"));
    }),
  ],
};

export const LoadError: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopProductRoute, { kind: "ingress", status: 504 });
    }),
  ],
};
