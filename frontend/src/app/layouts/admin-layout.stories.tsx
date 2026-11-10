import type { Meta, StoryObj } from "@storybook/react-vite";

import { AdminLayout } from "@/app/layouts/admin-layout";
import { getCurrentSessionRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";
import { LayoutInRouter } from "@/test/story-router";

const meta = {
  title: "App/AdminLayout",
  component: AdminLayout,
  parameters: { layout: "fullscreen", hasOwnRouter: true },
  render: () => <LayoutInRouter layout={<AdminLayout />} />,
} satisfies Meta<typeof AdminLayout>;

export default meta;

type Story = StoryObj<typeof meta>;

export const SignedInAsAdmin: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "admin"));
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
