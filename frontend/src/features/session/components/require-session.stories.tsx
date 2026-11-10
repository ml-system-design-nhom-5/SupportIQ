import type { Meta, StoryObj } from "@storybook/react-vite";

import { RequireSession } from "@/features/session/components/require-session";
import { getCurrentSessionRoute } from "@/test/backend-routes";
import { exampleAnswer } from "@/test/fake-backend";
import { withFakeBackend } from "@/test/story-backend";

const meta = {
  title: "Session/RequireSession",
  component: RequireSession,
  parameters: { layout: "fullscreen" },
  args: { children: () => null },
} satisfies Meta<typeof RequireSession>;

export default meta;

type Story = StoryObj<typeof meta>;

export const SessionCheckFailed: Story = {
  decorators: [
    withFakeBackend((backend) => {
      backend.answer(getCurrentSessionRoute, exampleAnswer(503, "problems", "not-ready"));
    }),
  ],
};
