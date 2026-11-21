import type { Meta, StoryObj } from "@storybook/react-vite";
import { expect } from "storybook/test";

import { OrdersPage } from "@/features/shop-orders/components/orders-page";
import { listShopOrdersRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Shop/My orders",
  component: OrdersPage,
} satisfies Meta<typeof OrdersPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const FirstPage: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "first-page"));
    }),
  ],
};

export const LastPageWithRefund: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "last-page"));
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, { kind: "no_answer" });
    }),
  ],
};

export const NoOrders: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "empty"));
    }),
  ],
};

export const PermissionDenied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(403, "problems", "forbidden-role"));
    }),
  ],
};

export const LoadError: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(500, "problems", "internal-error"));
    }),
  ],
};

export const LoadingMore: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "first-page"), {
        kind: "no_answer",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more orders" }));

    await expect(await canvas.findByRole("button", { name: "Loading…" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  },
};

export const LoadingMoreFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(listShopOrdersRoute, exampleAnswer(200, "listShopOrders", "first-page"), {
        kind: "network_error",
      });
    }),
  ],
  play: async ({ canvas, userEvent }) => {
    await userEvent.click(await canvas.findByRole("button", { name: "Show more orders" }));

    await expect(await canvas.findByRole("alert")).toHaveTextContent(
      "More orders could not be loaded.",
    );
  },
};
