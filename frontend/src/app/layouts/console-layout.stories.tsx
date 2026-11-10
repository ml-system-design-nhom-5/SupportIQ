import type { Meta, StoryObj } from "@storybook/react-vite";

import { ConsoleLayout } from "@/app/layouts/console-layout";
import { getCurrentSessionRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "App/ConsoleLayout",
  component: ConsoleLayout,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof ConsoleLayout>;

export default meta;

type Story = StoryObj<typeof meta>;

export const SignedInAsStaff: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getCurrentSessionRoute, exampleAnswer(200, "getCurrentSession", "staff"));
    }),
  ],
};
