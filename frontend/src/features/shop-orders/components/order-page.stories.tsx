import type { Meta, StoryObj } from "@storybook/react-vite";

import { OrderPage } from "@/features/shop-orders/components/order-page";
import { OrderSupportSection } from "@/features/shop-support";
import { getShopOrderRoute, listShopTicketsRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Shop/Order",
  component: OrderPage,
  args: {
    orderId: "ORD-20931",
    renderSupport: (messageBoxId) => (
      <OrderSupportSection orderId="ORD-20931" messageBoxId={messageBoxId} />
    ),
  },
} satisfies Meta<typeof OrderPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const RefundUnderReview: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "refund-under-review"));
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "last-page"));
    }),
  ],
};

export const InTransitWithoutTickets: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopOrderRoute, exampleAnswer(200, "getShopOrder", "in-transit"));
      backend.answer(listShopTicketsRoute, exampleAnswer(200, "listShopTickets", "empty"));
    }),
  ],
};

export const Loading: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopOrderRoute, { kind: "no_answer" });
    }),
  ],
};

export const NotFound: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopOrderRoute, exampleAnswer(404, "problems", "not-found"));
    }),
  ],
};

export const PermissionDenied: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopOrderRoute, exampleAnswer(403, "problems", "forbidden-role"));
    }),
  ],
};

export const LoadError: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getShopOrderRoute, { kind: "network_error" });
    }),
  ],
};
