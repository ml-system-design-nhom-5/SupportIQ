import type { Meta, StoryObj } from "@storybook/react-vite";

import { StartPage } from "@/features/session/components/start-page";
import { getCurrentSessionRoute } from "@/test/backend-routes";
import { readExampleWith } from "@/test/contract-examples";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Session/StartPage",
  component: StartPage,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof StartPage>;

export default meta;

type Story = StoryObj<typeof meta>;

export const RoleWithoutAnArea: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getCurrentSessionRoute, {
        kind: "body",
        status: 200,
        body: readExampleWith("getCurrentSession", "customer", { role: "a_later_role" }),
      });
    }),
  ],
};
