import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { ProductsPage } from "@/features/shop-catalog/components/products-page";
import { listShopProductsRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Shop/Products",
  component: ProductsPage,
} satisfies Meta<typeof ProductsPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FirstPage: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(200, "listShopProducts", "first-page"));
    }),
  ],
};

export const LastPage: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(200, "listShopProducts", "last-page"));
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, { kind: "no_answer" });
    }),
  ],
};

export const NoProducts: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(200, "listShopProducts", "empty"));
    }),
  ],
};

export const PermissionDenied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(403, "problems", "forbidden-role"));
    }),
  ],
};

export const LoadError: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(503, "problems", "not-ready"));
    }),
  ],
};

export const LoadingMore: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(200, "listShopProducts", "first-page"), {
        kind: "no_answer",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more products" }));

    await expect(await canvas.findByRole("button", { name: "Loading…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  },
};

export const LoadingMoreFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopProductsRoute, exampleAnswer(200, "listShopProducts", "first-page"), {
        kind: "network_error",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more products" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "More products could not be loaded.",
    );
  },
};
