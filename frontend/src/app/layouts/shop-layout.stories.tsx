import type { Meta, StoryObj } from "@storybook/react-vite";

import { ShopLayout } from "@/app/layouts/shop-layout";
import { getCurrentSessionRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";
import { LayoutInRouter } from "@/test/story-router";

const meta = {
  title: "App/ShopLayout",
  component: ShopLayout,
  parameters: { layout: "fullscreen", hasOwnRouter: true },
  render: () => <LayoutInRouter layout={<ShopLayout />} />,
} satisfies Meta<typeof ShopLayout>;

export default meta;

type Story = StoryObj<typeof meta>;

export const SignedInAsCustomer: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "customer"));
    }),
  ],
};

export const SignedInWithAnotherRole: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "staff"));
    }),
  ],
};
